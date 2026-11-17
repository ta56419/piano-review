"""File orchestration: inference -> reference alignment -> explicit JSON report."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .alignment import align_notes
from .reference import parse_midi
from .scoring import score_alignment
from .transcription import extract_audio, transcribe, sha256, DEFAULT_DECODER, DECODERS
from .comparison import build_comparisons

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run_analysis(sample: str, reuse_transcription: bool = False) -> dict:
    if sample not in {"real", "controlled"}:
        raise ValueError("sample must be real or controlled")
    source = ROOT / "data" / ("real.mp4" if sample == "real" else "controlled.wav")
    notes_path = ROOT / "reports" / f"{sample}-notes.json"
    audio_path = ROOT / "reports" / f"{sample}-notes.wav"
    metadata = extract_audio(source, audio_path)
    if reuse_transcription and notes_path.is_file():
        transcription = json.loads(notes_path.read_text(encoding="utf-8"))
        if transcription["audio_sha256"] != sha256(audio_path):
            raise ValueError("Cached transcription belongs to different audio; rerun without --reuse-transcription")
        if transcription.get("decoder") != DEFAULT_DECODER or any(
            transcription.get("settings", {}).get(key) != value for key, value in DECODERS[DEFAULT_DECODER].items()
        ):
            raise ValueError("Cached decoder settings are stale; rerun without --reuse-transcription")
    else:
        transcription = transcribe(audio_path, notes_path)
    reference = parse_midi(ROOT / "data" / "reference.mid")
    alignment = align_notes(reference, transcription["notes"], metadata["duration"])
    score = score_alignment(reference, transcription["notes"], alignment,
                            evidence="model" if sample == "real" else "controlled_audio")
    comparisons = build_comparisons(reference, transcription["notes"], alignment, score["findings"])
    write_json(ROOT / "reports" / f"{sample}-analysis.json", score)
    measures = [{**m, "measure": m["number"],
                 "status": {"clear": "clean", "review": "uncertain"}.get(m["status"], m["status"]),
                 "error_count": m["confirmed_errors"]} for m in score["measures"]]
    findings = [{**f, "kind": f["type"], "title": f["description"],
                 "explanation": f["reason"],
                 "expected": f["expected_name"] if f["type"] != "timing" else f'{f["expected_onset"]:.3f} с',
                 "observed": f["observed_name"] if f["type"] != "timing" else f'{f["observed_onset"]:.3f} с'}
                for f in score["findings"]]
    limitations = [
        "Педаль и обертоны могут давать повторные или лишние ноты.",
        "Свободный темп иногда выглядит как раннее или позднее вступление.",
    ]
    if sample == "real":
        limitations.insert(0, "Совпадение модели с MIDI — не оценка пианиста.")
    report = {
        "schema_version": 2, "sample": sample, "title": "Прелюдия до мажор · BWV 846",
        "media_url": "/media/real.mp4" if sample == "real" else "/media/controlled.wav",
        "duration": metadata["duration"], "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": transcription["model"], "media": metadata,
        "decoder": {"name": transcription["decoder"], "settings": transcription["settings"]},
        "debug": {"raw_detections_url": f"/api/raw?sample={sample}",
                  "decoder_comparison_url": "/api/decoder-comparison"},
        "excerpt": {"start_measure": alignment["first_matched_measure"],
                    "end_measure": alignment["last_matched_measure"],
                    "confidence": alignment["confidence"],
                    "label": f'Такты {alignment["first_matched_measure"]}–{alignment["last_matched_measure"]} · 4/4'},
        "summary": {"accuracy": score["accuracy"], "accuracy_label": score["accuracy_label"],
                    "model_agreement": score.get("model_agreement", score["accuracy"]),
                    "accuracy_is_estimate": score["accuracy_is_estimate"],
                    "accuracy_interval": score["accuracy_interval"],
                    "error_count": score["confirmed_error_count"],
                    "uncertain_count": score["uncertain_count"], "breakdown": score["breakdown"],
                    "problem_measures": score["problem_measures"], "review_measures": score["review_measures"],
                    "advice": score["advice"], "expected_note_count": score["expected_note_count"],
                    "pitch_match_count": sum(m["pitch_matches"] for m in comparisons),
                    "verification_status": "unverified_performance" if sample == "real" else "controlled_audio"},
        "measures": measures, "comparisons": comparisons, "findings": findings,
        "scoring": {"description": "Совпадение с MIDI = 100 × (1 − расхождения / (ноты партитуры + лишние ноты)). Замена считается один раз. Непроверенные ноты влияют на это совпадение, но не на число подтверждённых ошибок.",
                    "timing_tolerance_ms": score["timing_tolerance_ms"],
                    "reference_note_count": score["expected_note_count"],
                    "scored_measures": score["scored_measures"],
                    "median_onset_residual_ms": alignment["median_onset_residual_ms"]},
        "limitations": limitations,
    }
    write_json(ROOT / "reports" / f"{sample}.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", choices=["real", "controlled", "all"], default="all")
    parser.add_argument("--reuse-transcription", action="store_true", help="Reuse hash-matched notes; default always runs model")
    args = parser.parse_args()
    for sample in ["real", "controlled"] if args.sample == "all" else [args.sample]:
        report = run_analysis(sample, args.reuse_transcription)
        print(json.dumps({"sample": sample, "summary": report["summary"], "excerpt": report["excerpt"]}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
