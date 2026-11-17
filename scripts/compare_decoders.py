"""Fresh inference; decoder comparison against score and independent synthetic notes."""
from pathlib import Path
import json
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from piano_review.transcription import extract_audio, transcribe
from piano_review.reference import parse_midi
from piano_review.alignment import align_notes
from piano_review.scoring import score_alignment
from piano_review.controlled import synthesize_piano, verify_controlled_report


def render_probe():
    """Quiet and rapid events are never deleted to improve a decoder's result."""
    events = []
    for group, start, pitches, spacing, velocity, duration in [
        ("normal", .6, [60, 64, 67, 72, 61, 65, 68, 73], .4, 82, .22),
        ("quiet", 4.4, [60, 64, 67, 72, 61, 65, 68, 73], .4, 24, .22),
        ("rapid_repeats", 8.2, [67] * 6 + [72] * 6, .18, 82, .10),
    ]:
        for index, pitch in enumerate(pitches):
            onset = round(start + index * spacing, 4)
            events.append({"group": group, "pitch": pitch, "onset": onset,
                           "offset": onset + duration, "velocity": velocity})
    path = ROOT / "data/decoder-probe.wav"
    synthesize_piano(events, path)
    truth = {"description": "8 normal, 8 quiet (-10.7 dB velocity gain), 12 same-pitch repeats at 180 ms spacing",
             "notes": events, "limitations": "Synthetic isolated articulation; not a real piano benchmark."}
    (ROOT / "data/decoder-probe-truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    return path, truth


def probe_metrics(expected, observed):
    available = set(range(len(observed)))
    matches = []
    for note in expected:
        candidates = [i for i in available if observed[i]["pitch"] == note["pitch"]
                      and abs(observed[i]["onset"] - note["onset"]) <= .065]
        if candidates:
            chosen = min(candidates, key=lambda i: abs(observed[i]["onset"] - note["onset"]))
            available.remove(chosen)
            matches.append(note)
    groups = {group: {"matched": sum(n["group"] == group for n in matches),
                      "expected": sum(n["group"] == group for n in expected)}
              for group in ("normal", "quiet", "rapid_repeats")}
    return {"groups": groups, "matched": len(matches), "expected": len(expected),
            "detected": len(observed), "unmatched_detections": len(available),
            "onset_tolerance_ms": 65}


def main():
    reference = parse_midi(ROOT / "data/reference.mid")
    result = {"fresh_inference": True, "comparison": {}}
    for sample in ("real", "controlled"):
        source = ROOT / "data" / ("real.mp4" if sample == "real" else "controlled.wav")
        metadata = extract_audio(source, ROOT / f"reports/{sample}-notes.wav")
        transcription = transcribe(ROOT / f"reports/{sample}-notes.wav", ROOT / f"reports/{sample}-notes.json")
        result["comparison"][sample] = {}
        for name, decoded in transcription["decoders"].items():
            alignment = align_notes(reference, decoded["notes"], metadata["duration"])
            score = score_alignment(reference, decoded["notes"], alignment,
                                    evidence="model" if sample == "real" else "controlled_audio")
            matches = sum(reference["notes"][p["reference_index"]]["pitch"] == decoded["notes"][p["observed_index"]]["pitch"]
                          for p in alignment["pairs"] if reference["notes"][p["reference_index"]]["measure"] in score["scored_measures"])
            entry = {"settings": decoded["settings"], "detected": len(decoded["notes"]),
                     "pitch_matches": matches, "expected_notes": score["expected_note_count"],
                     "confirmed": score["breakdown"], "uncertain": score["uncertain_breakdown"],
                     "accuracy": score["accuracy"], "scored_measures": score["scored_measures"]}
            if sample == "controlled":
                truth = json.loads((ROOT / "data/controlled-truth.json").read_text(encoding="utf-8"))
                entry["fixture_check"] = verify_controlled_report(score, truth)
            result["comparison"][sample][name] = entry
    path, truth = render_probe()
    transcription = transcribe(path, ROOT / "reports/decoder-probe-notes.json")
    result["comparison"]["probe"] = {name: probe_metrics(truth["notes"], decoded["notes"])
                                        for name, decoded in transcription["decoders"].items()}
    (ROOT / "reports/decoder-comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
