"""Build inspectable per-measure note pairs without discarding model detections."""
from .scoring import note_name


def build_comparisons(reference: dict, notes: list[dict], alignment: dict, findings: list[dict]) -> list[dict]:
    pairs = {pair["reference_index"]: pair for pair in alignment["pairs"]}
    paired_observations = {pair["observed_index"] for pair in alignment["pairs"]}
    results = []
    for measure in alignment["measures"]:
        if not measure["scored"]:
            continue
        number = measure["number"]
        expected_notes, detected_notes, events = [], [], []
        for index, note in enumerate(reference["notes"]):
            if note["measure"] != number:
                continue
            expected = {"id": f"reference-{index}", "pitch": note["pitch"], "name": note_name(note["pitch"]),
                        "onset": round(alignment["slope"] * note["onset"] + alignment["intercept"], 6),
                        "offset": round(alignment["slope"] * note["offset"] + alignment["intercept"], 6),
                        "beat": note["beat"], "reference_index": index}
            pair = pairs.get(index)
            observed = None
            if pair:
                observed_index = pair["observed_index"]
                observed = {**notes[observed_index], "id": f"detected-{observed_index}",
                            "name": note_name(notes[observed_index]["pitch"]),
                            "observed_index": observed_index, "reference_id": expected["id"]}
                detected_notes.append(observed)
            associated = [f for f in findings if f["reference_index"] == index]
            events.append({"id": expected["id"], "expected": expected, "observed": observed,
                           "pitch_match": observed is not None and expected["pitch"] == observed["pitch"],
                           "delta_ms": round((observed["onset"] - expected["onset"]) * 1000) if observed else None,
                           "finding_ids": [f["id"] for f in associated],
                           "status": associated[0]["status"] if associated else "matched",
                           "kind": associated[0]["type"] if associated else "match"})
            expected_notes.append(expected)
        extras = []
        for index, note in enumerate(notes):
            if index not in paired_observations and measure["mapped_start"] <= note["onset"] < measure["mapped_end"]:
                observed = {**note, "id": f"detected-{index}", "name": note_name(note["pitch"]),
                            "observed_index": index, "reference_id": None}
                extras.append(observed)
                detected_notes.append(observed)
        results.append({"measure": number, "start": measure["start"], "end": measure["end"],
                        "reference_notes": expected_notes,
                        "detected_notes": sorted(detected_notes, key=lambda n: (n["onset"], n["pitch"])),
                        "events": events, "extra_detections": extras,
                        "pitch_matches": sum(event["pitch_match"] for event in events),
                        "reference_count": len(expected_notes),
                        "findings": [f["id"] for f in findings if f["measure"] == number]})
    return results
