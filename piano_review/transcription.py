"""FFmpeg extraction and real Basic Pitch ONNX inference, independent of scoring."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import time
import wave

DECODERS = {
    "baseline": {"onset_thresh": 0.50, "frame_thresh": 0.30, "infer_onsets": True,
                 "melodia_trick": True},
    "candidate": {"onset_thresh": 0.60, "frame_thresh": 0.30, "infer_onsets": False,
                  "melodia_trick": False},
}
DEFAULT_DECODER = "candidate"


def decode_outputs(outputs: dict, profile: str):
    """Decode without consulting the score or mutating the saved model arrays."""
    import numpy as np
    from basic_pitch.note_creation import model_output_to_notes
    from basic_pitch.constants import AUDIO_SAMPLE_RATE, FFT_HOP

    if profile not in DECODERS:
        raise ValueError(f"Unknown decoder: {profile}")
    settings = {**DECODERS[profile], "min_note_len": int(np.round(.08 * AUDIO_SAMPLE_RATE / FFT_HOP)),
                "min_freq": 27.5, "max_freq": 4186.01, "include_pitch_bends": False}
    midi, events = model_output_to_notes({key: value.copy() for key, value in outputs.items()}, **settings)
    notes = sorted([
        {"pitch": int(pitch), "onset": round(float(start), 6),
         "offset": round(float(end), 6), "confidence": round(float(amplitude), 6)}
        for start, end, pitch, amplitude, _ in events
    ], key=lambda note: (note["onset"], note["pitch"]))
    return midi, notes, settings


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_audio(source: Path, output: Path) -> dict:
    import imageio_ffmpeg

    if not source.is_file():
        raise ValueError(f"Media file does not exist: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
        "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "22050",
        "-c:a", "pcm_s16le", str(output),
    ], check=True, capture_output=True)
    with wave.open(str(output), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
    return {"duration": duration, "sample_rate": 22050, "source_sha256": sha256(source),
            "audio_sha256": sha256(output), "ffmpeg_version": imageio_ffmpeg.get_ffmpeg_version()}


def transcribe(audio_path: Path, output_path: Path, profile: str = DEFAULT_DECODER) -> dict:
    import numpy as np
    import basic_pitch
    from basic_pitch.inference import Model, run_inference

    started = time.perf_counter()
    model_path = Path(basic_pitch.__file__).parent / "saved_models" / "icassp_2022" / "nmp.onnx"
    model = Model(model_path)
    outputs = run_inference(str(audio_path), model)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output_path.with_suffix(".npz"), **outputs)
    decoded = {}
    for name in DECODERS:
        midi, notes, settings = decode_outputs(outputs, name)
        decoded[name] = {"settings": settings, "notes": notes}
        if name == profile:
            midi.write(str(output_path.with_suffix(".mid")))
    if profile not in decoded:
        raise ValueError(f"Unknown decoder: {profile}")
    result = {
        "model": {"name": "Spotify Basic Pitch / ICASSP 2022 (ONNX CPU)",
                  "version": importlib.metadata.version("basic-pitch"),
                  "runtime": importlib.metadata.version("onnxruntime"),
                  "sha256": sha256(model_path)},
        "decoder": profile, "settings": decoded[profile]["settings"],
        "audio_sha256": sha256(audio_path), "decoders": decoded,
        "elapsed_seconds": round(time.perf_counter() - started, 3), "notes": decoded[profile]["notes"],
        "confidence_note": "Mean model activation, not a calibrated probability of correctness.",
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    audio_path = arguments.output.with_suffix(".wav")
    metadata = extract_audio(arguments.source, audio_path)
    print(json.dumps(metadata), flush=True)
    result = transcribe(audio_path, arguments.output)
    print(json.dumps({"notes": len(result["notes"]), "seconds": result["elapsed_seconds"], "model": result["model"]}), flush=True)
