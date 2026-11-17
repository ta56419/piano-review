"""Subsequence note matching followed by one robust global tempo fit."""

from __future__ import annotations

import math

import numpy as np


def validate_notes(notes: list[dict]) -> list[dict]:
    result = []
    for index, note in enumerate(notes):
        pitch = note.get("pitch")
        onset = note.get("onset")
        offset = note.get("offset", onset)
        confidence = note.get("confidence", 1.0)
        if not isinstance(pitch, (int, np.integer)) or not 0 <= pitch <= 127:
            raise ValueError(f"Note {index}: pitch must be an integer MIDI note")
        if not all(isinstance(value, (int, float, np.number)) and math.isfinite(value)
                   for value in (onset, offset, confidence)):
            raise ValueError(f"Note {index}: onset, offset and confidence must be finite")
        if onset < 0 or offset < onset or not 0 <= confidence <= 1:
            raise ValueError(f"Note {index}: invalid onset, offset or confidence")
        result.append({**note, "pitch": int(pitch), "onset": float(onset),
                       "offset": float(offset), "confidence": float(confidence),
                       "input_index": index})
    result.sort(key=lambda note: (note["onset"], note["pitch"]))
    return result


def _ordered_match(reference: list[dict], observed: list[dict], slope=None, intercept=None):
    """Semi-global edit alignment: the entire recording may match any score excerpt."""
    rows, columns = len(observed), len(reference)
    costs = np.empty((rows + 1, columns + 1), dtype=np.float64)
    moves = np.zeros((rows + 1, columns + 1), dtype=np.uint8)
    costs[0, :] = 0.0  # Score material before the clip is not a missing-note error.
    costs[:, 0] = np.arange(rows + 1) * 0.90
    moves[1:, 0] = 1
    ref_pitch = np.array([note["pitch"] for note in reference])
    ref_time = np.array([note["onset"] for note in reference])
    for i, note in enumerate(observed, 1):
        pair_costs = np.where(ref_pitch == note["pitch"], 0.0, 1.25)
        if slope is not None:
            residual = np.abs(note["onset"] - (slope * ref_time + intercept))
            # Do not warp each note to its nearest onset: timing residuals remain measurable.
            pair_costs = pair_costs + np.minimum(residual / 0.40, 3.0) * 0.35
            pair_costs[residual > 0.85] = 3.5
        for j in range(1, columns + 1):
            options = (costs[i - 1, j - 1] + pair_costs[j - 1],
                       costs[i - 1, j] + 0.90,
                       costs[i, j - 1] + 0.90)
            move = min(range(3), key=options.__getitem__)
            costs[i, j] = options[move]
            moves[i, j] = move
    end = int(np.argmin(costs[rows, 1:])) + 1
    i, j = rows, end
    pairs, extra, missing = [], [], []
    while i > 0:
        move = int(moves[i, j]) if j else 1
        if move == 0:
            pairs.append((j - 1, i - 1))
            i, j = i - 1, j - 1
        elif move == 1:
            extra.append(i - 1)
            i -= 1
        else:
            missing.append(j - 1)
            j -= 1
    pairs.reverse()
    alternatives = [float(costs[rows, endpoint]) for endpoint in range(1, columns + 1)
                    if abs(endpoint - end) >= 16]
    margin = (min(alternatives) - float(costs[rows, end])) / max(1, rows) if alternatives else 1.0
    return pairs, sorted(missing), sorted(extra), float(costs[rows, end]), margin


def _fit_global_time(reference, observed, pairs):
    exact = [(r, o) for r, o in pairs if reference[r]["pitch"] == observed[o]["pitch"]]
    if len(exact) < 6:
        raise ValueError("Too few matching notes to locate this excerpt")
    x = np.array([reference[r]["onset"] for r, _ in exact])
    y = np.array([observed[o]["onset"] for _, o in exact])
    distance = x[:, None] - x[None, :]
    differences = y[:, None] - y[None, :]
    span = max(float(np.ptp(x)) * 0.25, 1.0)
    eligible = distance >= span
    slopes = differences[eligible] / distance[eligible]
    slopes = slopes[(slopes >= 0.4) & (slopes <= 2.5)]
    if not len(slopes):
        raise ValueError("Tempo ratio is outside the supported 0.4–2.5 range")
    slope = float(np.median(slopes))
    intercept = float(np.median(y - slope * x))
    residual = y - slope * x - intercept
    # Only global inlier regression; this cannot absorb an isolated early/late note.
    cutoff = max(0.08, min(0.25, 3 * float(np.median(np.abs(residual)))))
    keep = np.abs(residual) <= cutoff
    if keep.sum() >= 6 and np.ptp(x[keep]) >= 1:
        slope, intercept = np.polyfit(x[keep], y[keep], 1)
        slope, intercept = float(slope), float(intercept)
    if not 0.4 <= slope <= 2.5:
        raise ValueError("Fitted tempo ratio is outside the supported range")
    return slope, intercept


def _repair_chord_order(reference, observed, pairs, missing, extra, slope, intercept):
    """Recover same-onset chord notes that arrive in a different pitch order."""
    pairs = list(pairs)
    remaining_missing, remaining_extra = set(missing), set(extra)
    for r in missing:
        candidates = [o for o in remaining_extra
                      if reference[r]["pitch"] == observed[o]["pitch"]
                      and abs(observed[o]["onset"] - (slope * reference[r]["onset"] + intercept)) < 0.10]
        if candidates:
            o = min(candidates, key=lambda o: abs(observed[o]["onset"] - (slope * reference[r]["onset"] + intercept)))
            pairs.append((r, o))
            remaining_missing.remove(r)
            remaining_extra.remove(o)
    # Swapped members of a simultaneous chord are matches, not substitutions.
    for a in range(len(pairs)):
        r1, o1 = pairs[a]
        if reference[r1]["pitch"] == observed[o1]["pitch"]:
            continue
        for b in range(a + 1, min(a + 8, len(pairs))):
            r2, o2 = pairs[b]
            if abs(reference[r1]["onset"] - reference[r2]["onset"]) > 0.02:
                continue
            if (reference[r1]["pitch"] == observed[o2]["pitch"]
                    and reference[r2]["pitch"] == observed[o1]["pitch"]
                    and abs(observed[o1]["onset"] - observed[o2]["onset"]) <= 0.10):
                pairs[a], pairs[b] = (r1, o2), (r2, o1)
                break
    return sorted(pairs), sorted(remaining_missing), sorted(remaining_extra)


def align_notes(reference: dict, detected_notes: list[dict], audio_duration: float | None = None) -> dict:
    """Locate an excerpt in the full piece and retain a fixed affine playback clock."""
    ref = reference["notes"]
    observed = validate_notes(detected_notes)
    if len(observed) < 8 or len(ref) < 8:
        raise ValueError("At least eight notes are required for excerpt alignment")
    if audio_duration is None:
        audio_duration = max(note["offset"] for note in observed)
    if not math.isfinite(audio_duration) or audio_duration <= 0:
        raise ValueError("audio_duration must be finite and positive")
    pairs, missing, extra, cost, location_margin = _ordered_match(ref, observed)
    slope, intercept = _fit_global_time(ref, observed, pairs)
    for _ in range(2):
        pairs, missing, extra, cost, _ = _ordered_match(ref, observed, slope, intercept)
        slope, intercept = _fit_global_time(ref, observed, pairs)
    pairs, missing, extra = _repair_chord_order(ref, observed, pairs, missing, extra, slope, intercept)
    exact = [(r, o) for r, o in pairs if ref[r]["pitch"] == observed[o]["pitch"]]
    residuals = [observed[o]["onset"] - (slope * ref[r]["onset"] + intercept) for r, o in exact]
    median_error = float(np.median(np.abs(residuals))) if residuals else 1.0
    first_ref = min(r for r, _ in pairs)
    last_ref = max(r for r, _ in pairs)
    reference_span = last_ref - first_ref + 1
    match_ratio = len(exact) / reference_span
    observed_precision = len(exact) / len(observed)
    # Extra detector fragments affect scoring, not the evidence that a long exact
    # reference subsequence occurs at a stable clock in this recording.
    confident = (match_ratio >= 0.70 and median_error <= 0.18 and len(exact) >= 16
                 and location_margin >= 0.005)
    aligned_measures = []
    for measure in reference["measures"]:
        start = slope * measure["start"] + intercept
        end = slope * measure["end"] + intercept
        if end < 0 or start > audio_duration:
            continue
        expected_count = sum(note["measure"] == measure["number"] for note in ref)
        match_count = sum(ref[r]["measure"] == measure["number"] for r, _ in exact)
        coverage = match_count / expected_count if expected_count else 0
        complete = start >= -0.045 and end <= audio_duration + 0.045
        scored = bool(complete and confident and coverage >= 0.55)
        aligned_measures.append({**measure, "start": round(max(0.0, start), 5),
                                 "end": round(min(audio_duration, end), 5),
                                 "mapped_start": start, "mapped_end": end,
                                 "complete": complete, "scored": scored,
                                 "match_coverage": round(coverage, 4),
                                 "expected_notes": expected_count})
    # Semi-global matching leaves both score ends free. Once the audio clock
    # proves a whole measure is present, its unmatched boundary notes are missing.
    scored_numbers = {m["number"] for m in aligned_measures if m["scored"]}
    paired_reference = {r for r, _ in pairs}
    missing = sorted(set(missing) | {r for r, note in enumerate(ref)
                                    if note["measure"] in scored_numbers and r not in paired_reference})
    return {"slope": slope, "intercept": intercept, "tempo_ratio": 1 / slope,
            "audio_duration": audio_duration, "confidence": "high" if confident else "low",
            "match_ratio": round(match_ratio, 4), "median_onset_residual_ms": round(median_error * 1000, 1),
            "observed_precision": round(observed_precision, 4),
            "location_margin": round(location_margin, 5),
            "pairs": [{"reference_index": r, "observed_index": observed[o]["input_index"],
                       "expected_onset": slope * ref[r]["onset"] + intercept,
                       "residual_seconds": observed[o]["onset"] - slope * ref[r]["onset"] - intercept}
                      for r, o in pairs],
            "missing_reference_indices": missing,
            "extra_observed_indices": [observed[o]["input_index"] for o in extra],
            "measures": aligned_measures,
            "scored_measures": [m["number"] for m in aligned_measures if m["scored"]],
            "first_matched_measure": ref[first_ref]["measure"],
            "last_matched_measure": ref[last_ref]["measure"],
            "method": "Pitch subsequence edit alignment + robust global affine time fit; no local warping",
            "alignment_cost": round(cost, 3)}
