"""Rebuild the labeled audio fixture. Its truth is never read by the analyzer."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from piano_review.controlled import render_controlled
from piano_review.reference import parse_midi

if __name__ == "__main__":
    truth = render_controlled(parse_midi(ROOT / "data/reference.mid"), 1, 3,
                              ROOT / "data/controlled.wav", ROOT / "data/controlled-truth.json")
    print(f"Rendered measures 1–3: {truth['audio']['duration']:.2f} seconds")
