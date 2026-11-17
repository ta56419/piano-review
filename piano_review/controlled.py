"""Deterministic audio fixture with two deliberate, independently recorded edits.

The truth file is only for verification. Transcription and scoring must receive
the rendered WAV and reference MIDI, never these edited note events.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import wave

import numpy as np


def build_fixture(
    reference: dict,
    start_measure: int,
    end_measure: int,
    *,
    seconds_per_beat: float = 1.2,
    leading_silence: float = 0.6,
    timing_delay: float = 0.2,
) -> tuple[list[dict], dict]:
    """Select whole source measures and edit exactly two distinct note events.

    A deliberately slow tempo leaves a perceptible gap after the delayed note.
    Original measure numbers remain in both events and the separate truth file.
    """
    if end_measure - start_measure < 2:
        raise ValueError("The controlled fixture needs at least three complete measures")
    if not 0.8 <= seconds_per_beat <= 2.0:
        raise ValueError("seconds_per_beat must be between 0.8 and 2.0")
    if leading_silence < 0 or not 0.15 <= timing_delay <= 0.22:
        raise ValueError("Use nonnegative silence and a delay between 0.15 and 0.22 s")
    measures = {int(m["number"]): m for m in reference["measures"]}
    requested = range(start_measure, end_measure + 1)
    if any(number not in measures for number in requested):
        raise ValueError("Requested measures are not in the MIDI reference")
    start_beat = float(measures[start_measure]["start_beat"])
    end_beat = float(measures[end_measure]["end_beat"])
    selected = sorted(
        (n for n in reference["notes"] if start_measure <= n["measure"] <= end_measure),
        key=lambda n: (n["beat"], n["pitch"]),
    )
    if not selected:
        raise ValueError("Requested measures contain no notes")
    events = []
    for index, note in enumerate(selected):
        onset = leading_silence + (float(note["beat"]) - start_beat) * seconds_per_beat
        duration = max(0.08, float(note["duration_beats"]) * seconds_per_beat)
        events.append({
            "index": index,
            "source_id": note.get("id", index),
            "pitch": int(note["pitch"]),
            "onset": round(onset, 6),
            "offset": round(onset + duration, 6),
            "measure": int(note["measure"]),
            "beat": float(note["beat"]),
            "velocity": 82,
        })

    def choose_note(number: int) -> dict:
        boundary = float(measures[number]["start_beat"])
        candidates = [
            event for event in events
            if event["measure"] == number and 1.0 <= event["beat"] - boundary <= 2.0
        ]
        if not candidates:
            candidates = [event for event in events if event["measure"] == number]
        # Prefer a clear treble event away from either excerpt boundary.
        return max(candidates, key=lambda event: (event["pitch"], -event["onset"]))

    wrong_note = choose_note(start_measure + 1)
    expected_pitch = wrong_note["pitch"]
    wrong_note["pitch"] += 1
    late_note = choose_note(start_measure + 2)
    expected_onset = late_note["onset"]
    late_note["onset"] = round(late_note["onset"] + timing_delay, 6)
    late_note["offset"] = round(late_note["offset"] + timing_delay, 6)
    truth = {
        "label": "Тестовый пример с намеренными ошибками",
        "purpose": "Verification fixture only; never an input to transcription or scoring",
        "renderer": "piano-review deterministic additive piano, version 2",
        "articulation": "Short 220 ms note gates; pitch and onset are evaluated, sustain duration is not",
        "source_measures": [start_measure, end_measure],
        "seconds_per_beat": seconds_per_beat,
        "leading_silence": leading_silence,
        "score_start": leading_silence,
        "score_end": leading_silence + (end_beat - start_beat) * seconds_per_beat,
        "edits": [
            {"kind": "pitch", "measure": wrong_note["measure"], "source_id": wrong_note["source_id"],
             "expected_pitch": expected_pitch, "observed_pitch": wrong_note["pitch"],
             "expected_onset": wrong_note["onset"], "observed_onset": wrong_note["onset"]},
            {"kind": "timing", "measure": late_note["measure"], "source_id": late_note["source_id"],
             "expected_pitch": late_note["pitch"], "observed_pitch": late_note["pitch"],
             "expected_onset": expected_onset, "observed_onset": late_note["onset"],
             "delta_ms": round(timing_delay * 1000)},
        ],
    }
    return events, truth


def synthesize_piano(events: list[dict], output_path: str | Path, *, minimum_duration: float = 0.0,
                     sample_rate: int = 22050, maximum_note_duration: float = 0.22) -> dict:
    """Render PCM audio with hammer attack and independently decaying harmonics.

    This is an original synthetic piano-like timbre, not a sampled instrument.
    No soundfont or external recording is needed or redistributed. Short note
    gates avoid synthetic held-bass retriggers in the transcription model. All
    pitches and onsets are preserved; pedal and sustain are outside this test.
    """
    if sample_rate < 16000 or not events or maximum_note_duration <= 0:
        raise ValueError("Use at least 16000 Hz, positive note duration, and one or more notes")
    if any(int(n["pitch"]) not in range(21, 109) or n["onset"] < 0 or n["offset"] <= n["onset"]
           for n in events):
        raise ValueError("Events require valid piano pitches and positive durations")
    duration = max(minimum_duration,
                   max(n["onset"] + min(n["offset"] - n["onset"], maximum_note_duration)
                       for n in events) + 0.8)
    audio = np.zeros(math.ceil(duration * sample_rate), dtype=np.float64)
    for note in events:
        held = min(float(note["offset"] - note["onset"]), maximum_note_duration)
        tail = 0.35
        time = np.arange(math.ceil((held + tail) * sample_rate), dtype=np.float64) / sample_rate
        frequency = 440 * 2 ** ((int(note["pitch"]) - 69) / 12)
        attack = 1 - np.exp(-time / 0.003)
        release = np.exp(-np.maximum(time - held, 0) / 0.065)
        tone = np.zeros_like(time)
        for harmonic, weight in enumerate((1.0, 0.48, 0.26, 0.13, 0.075, 0.045, 0.025), start=1):
            if frequency * harmonic >= sample_rate / 2:
                break
            decay = np.exp(-time * (0.50 + 0.32 * harmonic))
            tone += weight * decay * np.sin(2 * np.pi * frequency * harmonic * time)
        tone *= attack * release * (int(note.get("velocity", 82)) / 127)
        start = round(float(note["onset"]) * sample_rate)
        count = min(len(tone), len(audio) - start)
        audio[start:start + count] += tone[:count]
    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio *= 0.85 / peak
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(np.round(audio * 32767).astype("<i2").tobytes())
    return {"duration": len(audio) / sample_rate, "sample_rate": sample_rate,
            "maximum_note_duration": maximum_note_duration,
            "event_count": len(events), "peak": round(float(np.max(np.abs(audio))), 6)}


def render_controlled(reference: dict, start_measure: int, end_measure: int,
                      output_wav: str | Path, truth_path: str | Path, **kwargs) -> dict:
    """Create the WAV consumed by the normal pipeline and separate test truth."""
    events, truth = build_fixture(reference, start_measure, end_measure, **kwargs)
    truth["audio"] = synthesize_piano(events, output_wav, minimum_duration=truth["score_end"] + 0.6)
    truth_path = Path(truth_path)
    truth_path.parent.mkdir(parents=True, exist_ok=True)
    truth_path.write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
    return truth


def verify_controlled_report(report: dict, truth: dict, *, onset_tolerance: float = 0.15) -> dict:
    """Read-only fixture evaluation: findings must have been derived from audio.

    A successful check does not relabel a finding or change a score. Report
    confidence and renderer truth are deliberately kept separate.
    """
    checks = []
    for edit in truth["edits"]:
        matches = []
        for finding in report.get("findings", []):
            if finding.get("kind", finding.get("type")) != edit["kind"] or finding.get("measure") != edit["measure"]:
                continue
            timestamp = finding.get("timestamp", finding.get("playback_time"))
            if timestamp is None or abs(float(timestamp) - edit["observed_onset"]) > onset_tolerance:
                continue
            if finding.get("expected_pitch") != edit["expected_pitch"] or finding.get("observed_pitch") != edit["observed_pitch"]:
                continue
            if edit["kind"] == "timing" and abs(float(finding.get("delta_ms", 0)) - edit["delta_ms"]) > 50:
                continue
            matches.append(finding.get("id"))
        checks.append({"kind": edit["kind"], "measure": edit["measure"],
                       "passed": bool(matches), "matching_finding_ids": matches})
    return {"passed": all(check["passed"] for check in checks), "checks": checks}
