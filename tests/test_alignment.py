"""Regression checks use note events, independently of the transcription model."""

import copy
import math
import unittest

from piano_review.alignment import align_notes, validate_notes
from piano_review.scoring import score_alignment


def reference_fixture():
    # Distinct bars avoid accidentally testing only a repeated opening figure.
    patterns = [[60, 64, 67, 72, 76, 67, 72, 76],
                [60, 62, 69, 74, 77, 69, 74, 77],
                [59, 62, 67, 74, 77, 67, 74, 77],
                [59, 60, 64, 67, 72, 64, 67, 72],
                [57, 60, 64, 67, 72, 64, 67, 72],
                [57, 62, 66, 69, 74, 66, 69, 74]]
    notes = []
    for measure, pattern in enumerate(patterns, 1):
        for step, pitch in enumerate(pattern * 2):
            onset = (measure - 1) * 4 + step / 4
            notes.append({"id": len(notes), "pitch": pitch, "onset": onset,
                          "offset": onset + 0.22, "duration": 0.22, "beat": onset,
                          "duration_beats": 0.22, "measure": measure})
    return {"notes": notes, "measures": [{"number": i, "start": (i - 1) * 4,
             "end": i * 4, "start_beat": (i - 1) * 4, "end_beat": i * 4}
            for i in range(1, 7)]}


def observed_fixture(reference, start=1, end=6, slope=1.0, lead=0.6):
    base = (start - 1) * 4
    notes = [{"pitch": note["pitch"], "onset": (note["onset"] - base) * slope + lead,
              "offset": (note["offset"] - base) * slope + lead, "confidence": 0.95}
             for note in reference["notes"] if start <= note["measure"] <= end]
    return notes, (end - start + 1) * 4 * slope + lead + 0.2


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.reference = reference_fixture()

    def report(self, notes, duration, evidence="test"):
        alignment = align_notes(self.reference, notes, duration)
        return score_alignment(self.reference, notes, alignment, evidence=evidence)

    def test_clean_and_leading_silence(self):
        notes, duration = observed_fixture(self.reference)
        report = self.report(notes, duration)
        self.assertEqual(report["confirmed_error_count"], 0)
        self.assertEqual(report["accuracy"], 100)
        self.assertAlmostEqual(report["alignment"]["intercept"], 0.6, places=4)

    def test_substitution_counts_once(self):
        notes, duration = observed_fixture(self.reference)
        notes[37]["pitch"] += 1
        report = self.report(notes, duration)
        self.assertEqual(report["breakdown"], {"pitch": 1, "timing": 0, "missing": 0, "extra": 0})
        self.assertEqual(report["findings"][0]["measure"], 3)

    def test_missing_note_uses_aligned_expected_onset(self):
        notes, duration = observed_fixture(self.reference)
        missing = notes.pop(37)
        report = self.report(notes, duration)
        self.assertEqual(report["breakdown"]["missing"], 1)
        self.assertAlmostEqual(report["findings"][0]["timestamp"], missing["onset"], places=3)

    def test_extra_note(self):
        notes, duration = observed_fixture(self.reference)
        notes.append({"pitch": 81, "onset": 9.72, "offset": 9.85, "confidence": 0.95})
        report = self.report(notes, duration)
        self.assertEqual(report["breakdown"]["extra"], 1)

    def test_late_onset_preserved_by_global_fit(self):
        notes, duration = observed_fixture(self.reference)
        notes[37]["onset"] += 0.18
        notes[37]["offset"] += 0.18
        report = self.report(notes, duration)
        self.assertEqual(report["breakdown"]["timing"], 1)
        self.assertAlmostEqual(report["findings"][0]["delta_ms"], 180, delta=2)

    def test_global_slower_tempo_is_not_error(self):
        notes, duration = observed_fixture(self.reference, slope=1.4)
        report = self.report(notes, duration)
        self.assertEqual(report["confirmed_error_count"], 0)
        self.assertAlmostEqual(report["alignment"]["slope"], 1.4, places=4)

    def test_mid_piece_excerpt_keeps_measure_numbers(self):
        notes, duration = observed_fixture(self.reference, start=3, end=5, slope=0.8)
        report = self.report(notes, duration)
        self.assertEqual(report["scored_measures"], [3, 4, 5])
        self.assertEqual(report["confirmed_error_count"], 0)

    def test_partial_last_bar_is_not_scored(self):
        notes, duration = observed_fixture(self.reference, start=2, end=5)
        duration -= 1.0
        notes = [note for note in notes if note["onset"] < duration]
        report = self.report(notes, duration)
        self.assertEqual(report["scored_measures"], [2, 3, 4])

    def test_model_findings_remain_uncertain(self):
        notes, duration = observed_fixture(self.reference)
        notes[37]["pitch"] += 1
        report = self.report(notes, duration, evidence="model")
        self.assertEqual(report["confirmed_error_count"], 0)
        self.assertEqual(report["uncertain_count"], 1)
        self.assertTrue(report["accuracy_is_estimate"])

    def test_clean_model_output_is_not_verified_performer_accuracy(self):
        notes, duration = observed_fixture(self.reference)
        report = self.report(notes, duration, evidence="model")
        self.assertEqual(report["model_agreement"], 100)
        self.assertIsNone(report["accuracy"])
        self.assertTrue(report["accuracy_is_estimate"])

    def test_review_notes_do_not_enter_confirmed_error_count(self):
        notes, duration = observed_fixture(self.reference)
        notes.append({"pitch": 81, "onset": 9.72, "offset": 9.85, "confidence": 0.95})
        report = self.report(notes, duration, evidence="model")
        self.assertEqual(report["uncertain_breakdown"]["extra"], 1)
        self.assertEqual(report["confirmed_error_count"], 0)
        self.assertEqual(sum(report["breakdown"].values()), 0)
        self.assertEqual(report["problem_measures"], [])
        self.assertIsNone(report["accuracy"])
        self.assertLess(report["model_agreement"], 100)

    def test_missing_boundary_notes_count_in_complete_measures(self):
        for index, measure in [(0, 1), (-1, 6)]:
            with self.subTest(index=index):
                notes, duration = observed_fixture(self.reference)
                missing = notes.pop(index)
                report = self.report(notes, duration)
                self.assertEqual(report["breakdown"]["missing"], 1)
                self.assertEqual(report["findings"][0]["measure"], measure)
                self.assertAlmostEqual(report["findings"][0]["timestamp"], missing["onset"], places=3)

    def test_simultaneous_chord_order(self):
        reference = copy.deepcopy(self.reference)
        reference["notes"][38]["onset"] = reference["notes"][37]["onset"]
        reference["notes"].sort(key=lambda note: (note["onset"], note["pitch"]))
        notes, duration = observed_fixture(reference)
        for note in notes:
            if abs(note["onset"] - 9.85) < 1e-6 and note["pitch"] == 67:
                note["onset"] += 0.025
        alignment = align_notes(reference, notes, duration)
        report = score_alignment(reference, notes, alignment, evidence="test")
        self.assertEqual(report["confirmed_error_count"], 0)

    def test_invalid_values_rejected(self):
        for value in (math.nan, -1):
            with self.subTest(onset=value), self.assertRaises(ValueError):
                validate_notes([{"pitch": 60, "onset": value, "offset": 1}])


if __name__ == "__main__":
    unittest.main()
