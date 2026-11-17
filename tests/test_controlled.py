import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from piano_review.controlled import build_fixture, render_controlled, verify_controlled_report


def reference_fixture():
    notes = []
    for measure in range(10, 13):
        for step, pitch in enumerate([60, 64, 67, 72, 76, 67, 72, 76] * 2):
            notes.append({"id": len(notes), "measure": measure, "pitch": pitch,
                          "beat": (measure - 1) * 4 + step / 4, "duration_beats": 0.25})
    return {"notes": notes, "measures": [
        {"number": m, "start_beat": (m - 1) * 4, "end_beat": m * 4} for m in range(10, 13)
    ]}


class ControlledFixtureTests(unittest.TestCase):
    def test_exactly_one_pitch_change_and_one_late_note(self):
        reference = reference_fixture()
        events, truth = build_fixture(reference, 10, 12)
        pitch_changes = [event for event, source in zip(events, reference["notes"])
                         if event["pitch"] != source["pitch"]]
        late_changes = [event for event, source in zip(events, reference["notes"])
                        if abs(event["onset"] - (0.6 + (source["beat"] - 36) * 1.2)) > 0.001]
        self.assertEqual(len(pitch_changes), 1)
        self.assertEqual(len(late_changes), 1)
        self.assertEqual(truth["edits"][0]["measure"], 11)
        self.assertEqual(truth["edits"][1]["measure"], 12)
        self.assertEqual(truth["edits"][1]["delta_ms"], 200)
        self.assertEqual(len(events), 48)

    def test_rendered_wav_contains_silence_then_nonclipping_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            wav_path = Path(directory) / "controlled.wav"
            truth_path = Path(directory) / "controlled-truth.json"
            truth = render_controlled(reference_fixture(), 10, 12, wav_path, truth_path)
            with wave.open(str(wav_path), "rb") as wav:
                self.assertEqual(wav.getframerate(), 22050)
                self.assertEqual(wav.getnchannels(), 1)
                audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
            self.assertTrue(np.all(audio[:int(0.6 * 22050)] == 0))
            self.assertGreater(np.sqrt(np.mean(audio.astype(float) ** 2)), 1000)
            self.assertLess(np.max(np.abs(audio.astype(int))), 32767)
            self.assertGreater(truth["audio"]["duration"], truth["score_end"])
            self.assertTrue(truth_path.exists())

    def test_report_check_does_not_invent_findings(self):
        _, truth = build_fixture(reference_fixture(), 10, 12)
        report = {"findings": []}
        self.assertFalse(verify_controlled_report(report, truth)["passed"])
        self.assertEqual(report, {"findings": []})
        report["findings"] = [
            {"id": str(index), "kind": edit["kind"], "measure": edit["measure"],
             "timestamp": edit["observed_onset"], "expected_pitch": edit["expected_pitch"],
             "observed_pitch": edit["observed_pitch"], "delta_ms": edit.get("delta_ms")}
            for index, edit in enumerate(truth["edits"])
        ]
        self.assertTrue(verify_controlled_report(report, truth)["passed"])

    def test_rejects_incomplete_fixture_range(self):
        with self.assertRaises(ValueError):
            build_fixture(reference_fixture(), 10, 11)


if __name__ == "__main__":
    unittest.main()
