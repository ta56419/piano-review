"""Explicit note-event scoring and Russian explanations, separate from inference."""

from __future__ import annotations

from collections import Counter
import math

import numpy as np


NOTE_NAMES = ("до", "до-диез", "ре", "ми-бемоль", "ми", "фа", "фа-диез",
              "соль", "ля-бемоль", "ля", "си-бемоль", "си")


def note_name(pitch: int) -> str:
    return f"{NOTE_NAMES[pitch % 12]}{pitch // 12 - 1}"


def score_alignment(reference: dict, detected_notes: list[dict], alignment: dict,
                    timing_tolerance: float = 0.12, evidence: str = "model") -> dict:
    """Count each affected note once; model-only findings remain review candidates.

    evidence='controlled_audio' permits strong isolated audio detections to be
    confirmed for the explicitly labeled generated recording. It receives no
    fixture truth, so the renderer cannot dictate the findings.
    """
    if not math.isfinite(timing_tolerance) or timing_tolerance <= 0:
        raise ValueError("timing_tolerance must be finite and positive")
    if evidence not in {"model", "controlled_audio", "verified_audio", "test"}:
        raise ValueError("Unsupported evidence source")
    ref = reference["notes"]
    scored_measures = set(alignment["scored_measures"])
    pairs = alignment["pairs"]
    findings = []
    exact_pairs = [pair for pair in pairs if ref[pair["reference_index"]]["pitch"] ==
                   detected_notes[pair["observed_index"]]["pitch"]]

    def confidence_for(note, onset, kind):
        if evidence == "model":
            return "uncertain", "Нужно переслушать. Модель могла ошибиться."
        if kind in {"missing", "extra"} and evidence != "test":
            return "uncertain", "Модель могла пропустить ноту или распознать её повторно."
        nearby = [pair for pair in exact_pairs if abs(pair["expected_onset"] - onset) < 1.6
                  and abs(pair["expected_onset"] - onset) > 0.02]
        stable = [pair for pair in nearby if abs(pair["residual_seconds"]) < timing_tolerance]
        high_signal = note is not None and note.get("confidence", 1) >= 0.65
        if evidence == "test" or (high_signal and len(stable) >= 3
                                  and len(stable) >= len(nearby) * 0.6):
            return "confirmed", "Проверено на тестовой записи." if evidence == "controlled_audio" else "Проверено по звуку."
        return "uncertain", "Соседние ноты распознаны неуверенно."

    def add(kind, measure, timestamp, expected_pitch=None, observed_pitch=None,
            expected_onset=None, observed_onset=None, note=None, reference_index=None,
            observed_index=None):
        if measure not in scored_measures:
            return
        status, reason = confidence_for(note, timestamp, kind)
        delay_ms = round((observed_onset - expected_onset) * 1000) if (
            observed_onset is not None and expected_onset is not None) else None
        expected_name = note_name(expected_pitch) if expected_pitch is not None else None
        observed_name = note_name(observed_pitch) if observed_pitch is not None else None
        if kind == "pitch":
            description = f"Такт {measure} · {NOTE_NAMES[observed_pitch % 12].capitalize()} вместо {NOTE_NAMES[expected_pitch % 12]}"
        elif kind == "timing":
            direction = "позже" if delay_ms > 0 else "раньше"
            name = NOTE_NAMES[observed_pitch % 12]
            description = (f"Такт {measure} · {name.capitalize()} прозвучала на {abs(delay_ms)} мс {direction}"
                           if status == "confirmed" else f"Такт {measure} · Проверьте начало {name}")
        elif kind == "missing":
            description = f"Такт {measure} · {expected_name.capitalize()} не распознана"
        else:
            description = f"Такт {measure} · {observed_name.capitalize()} — на проверку"
        findings.append({"id": f"f{len(findings) + 1:03}", "type": kind,
                         "status": status, "measure": measure,
                         "timestamp": round(max(0, timestamp), 4),
                         "expected_pitch": expected_pitch, "observed_pitch": observed_pitch,
                         "expected_name": expected_name, "observed_name": observed_name,
                         "expected_onset": round(expected_onset, 4) if expected_onset is not None else None,
                         "observed_onset": round(observed_onset, 4) if observed_onset is not None else None,
                         "delta_ms": delay_ms, "description": description,
                         "reason": reason, "confidence": note.get("confidence") if note else None,
                         "reference_index": reference_index, "observed_index": observed_index})

    for pair in pairs:
        r, o = pair["reference_index"], pair["observed_index"]
        expected, observed = ref[r], detected_notes[o]
        if expected["pitch"] != observed["pitch"]:
            add("pitch", expected["measure"], observed["onset"], expected["pitch"],
                observed["pitch"], pair["expected_onset"], observed["onset"], observed, r, o)
        elif abs(pair["residual_seconds"]) > timing_tolerance:
            add("timing", expected["measure"], observed["onset"], expected["pitch"],
                observed["pitch"], pair["expected_onset"], observed["onset"], observed, r, o)
    for r in alignment["missing_reference_indices"]:
        expected = ref[r]
        onset = alignment["slope"] * expected["onset"] + alignment["intercept"]
        add("missing", expected["measure"], onset, expected_pitch=expected["pitch"],
            expected_onset=onset, reference_index=r)
    for o in alignment["extra_observed_indices"]:
        observed = detected_notes[o]
        measure = next((m["number"] for m in alignment["measures"]
                        if m["mapped_start"] <= observed["onset"] < m["mapped_end"]), None)
        if measure is not None:
            add("extra", measure, observed["onset"], observed_pitch=observed["pitch"],
                observed_onset=observed["onset"], note=observed, observed_index=o)
    findings.sort(key=lambda finding: (finding["timestamp"], finding["type"]))
    confirmed = [finding for finding in findings if finding["status"] == "confirmed"]
    uncertain = [finding for finding in findings if finding["status"] == "uncertain"]
    expected_count = sum(note["measure"] in scored_measures for note in ref)
    extras = sum(finding["type"] == "extra" for finding in findings)
    opportunities = expected_count + extras
    agreement = round(max(0, 100 * (1 - len(findings) / opportunities)), 1) if opportunities else None
    upper = round(max(0, 100 * (1 - len(confirmed) / opportunities)), 1) if opportunities else None
    breakdown = {kind: sum(finding["type"] == kind for finding in confirmed)
                 for kind in ("pitch", "timing", "missing", "extra")}
    uncertain_breakdown = {kind: sum(finding["type"] == kind for finding in uncertain)
                           for kind in breakdown}
    problem_measures = sorted({finding["measure"] for finding in confirmed})
    review_measures = sorted({finding["measure"] for finding in uncertain})
    measures = []
    for measure in alignment["measures"]:
        measure_findings = [finding for finding in findings if finding["measure"] == measure["number"]]
        status = "excluded" if not measure["scored"] else "review" if any(
            finding["status"] == "uncertain" for finding in measure_findings) else "error" if measure_findings else "clear"
        measures.append({**measure, "status": status, "confirmed_errors": sum(
            finding["status"] == "confirmed" for finding in measure_findings),
            "uncertain_count": sum(finding["status"] == "uncertain" for finding in measure_findings)})
    advice = []
    if problem_measures:
        joined = ", ".join(str(number) for number in problem_measures)
        advice.append(f"Повторите такты {joined} медленнее под метроном.")
        if breakdown["pitch"]:
            pitch_findings = [f for f in confirmed if f["type"] == "pitch"]
            first = pitch_findings[0]
            advice.append(f"Такт {first['measure']}: сверьте {NOTE_NAMES[first['expected_pitch'] % 12]} с партитурой.")
        if breakdown["timing"]:
            timing_measures = ", ".join(str(m) for m in sorted({f["measure"] for f in confirmed if f["type"] == "timing"}))
            label = "Такт" if "," not in timing_measures else "Такты"
            advice.append(f"{label} {timing_measures}: сыграйте шестнадцатые ровно, без задержек.")
    elif uncertain:
        advice.append("Переслушайте отмеченные ноты перед следующей попыткой.")
        advice.append("Для повторной проверки сделайте запись без фонового звука.")
    else:
        advice.append("Расхождений не найдено. Повторите фрагмент в том же темпе.")
    unverified = bool(uncertain) or evidence == "model"
    return {"accuracy": agreement if not unverified else None,
            "model_agreement": agreement,
            "accuracy_label": "Точность" if not unverified else "Точность не подтверждена",
            "accuracy_is_estimate": unverified, "accuracy_interval": [agreement, upper],
            "confirmed_error_count": len(confirmed), "uncertain_count": len(uncertain),
            "breakdown": breakdown, "uncertain_breakdown": uncertain_breakdown,
            "expected_note_count": expected_count, "scoring_opportunities": opportunities,
            "problem_measures": problem_measures, "review_measures": review_measures,
            "scored_measures": sorted(scored_measures), "measures": measures,
            "findings": findings, "advice": advice,
            "timing_tolerance_ms": round(timing_tolerance * 1000),
            "alignment": alignment, "evidence": evidence,
            "scoring_rule": "100 × (1 − affected note events / (reference notes + extra notes)). "
                            "A substitution counts once; a simultaneous timing difference is not counted twice. "
                            "Only complete confidently aligned measures are scored. "
                            "Uncertain detections lower the provisional agreement, not the confirmed error count; "
                            "the interval treats all uncertain detections as errors / none as errors."}
