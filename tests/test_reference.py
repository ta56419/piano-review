"""MIDI tempo and meter changes must preserve the score's time grid."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import mido
from piano_review.reference import parse_midi


class ReferenceTests(unittest.TestCase):
    def test_tempo_and_meter_changes_keep_original_measures(self):
        midi = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        midi.tracks.append(track)
        track.extend([
            mido.MetaMessage("set_tempo", tempo=500000),
            mido.MetaMessage("time_signature", numerator=4, denominator=4),
            mido.Message("note_on", note=60, velocity=80),
            mido.Message("note_off", note=60, time=1920),
            mido.MetaMessage("set_tempo", tempo=1000000),
            mido.MetaMessage("time_signature", numerator=3, denominator=4),
            mido.Message("note_on", note=64, velocity=80),
            mido.Message("note_off", note=64, time=1440),
            mido.Message("note_on", note=67, velocity=80),
            mido.Message("note_off", note=67, time=1440),
        ])
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "changes.mid"
            midi.save(path)
            reference = parse_midi(path)
        self.assertEqual([n["measure"] for n in reference["notes"]], [1, 2, 3])
        self.assertEqual([n["onset"] for n in reference["notes"]], [0, 2, 5])
        self.assertEqual([m["end_beat"] for m in reference["measures"]], [4, 7, 10])
        self.assertEqual(reference["tempo_changes"][-1]["bpm"], 60)

    def test_reference_matches_score_opening_and_sharps(self):
        reference = parse_midi(Path(__file__).resolve().parents[1] / "data/reference.mid")
        opening = [n["pitch"] for n in reference["notes"] if n["measure"] == 1]
        self.assertEqual(opening, [60, 64, 67, 72, 76, 67, 72, 76] * 2)
        for measure in [6, 10]:
            self.assertIn(66, [n["pitch"] for n in reference["notes"] if n["measure"] == measure])
