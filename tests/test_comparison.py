"""Check the browser adapter keeps notes, timing and uncertainty intact."""
import unittest
from piano_review.comparison import build_comparisons


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.reference = {"notes": [
            {"pitch": 60, "onset": 0, "offset": .5, "measure": 2, "beat": 1},
            {"pitch": 64, "onset": 1, "offset": 1.5, "measure": 2, "beat": 2},
        ]}
        self.notes = [
            {"pitch": 61, "onset": .9, "offset": 1.4, "confidence": .8},
            {"pitch": 72, "onset": 2, "offset": 2.3, "confidence": .4},
        ]
        self.alignment = {"slope": 2, "intercept": 1,
            "pairs": [{"reference_index": 0, "observed_index": 0}],
            "measures": [{"number": 2, "scored": True, "start": 1, "end": 9,
                          "mapped_start": 1, "mapped_end": 9}]}
        self.findings = [
            {"id": "pitch", "reference_index": 0, "measure": 2, "status": "uncertain", "type": "pitch"},
            {"id": "missing", "reference_index": 1, "measure": 2, "status": "uncertain", "type": "missing"},
        ]

    def test_pairs_keep_raw_onsets_and_expected_clock(self):
        result = build_comparisons(self.reference, self.notes, self.alignment, self.findings)[0]
        first, missing = result["events"]
        self.assertEqual(first["expected"]["onset"], 1)
        self.assertEqual(first["observed"]["onset"], .9)
        self.assertEqual(first["delta_ms"], -100)
        self.assertEqual(first["status"], "uncertain")
        self.assertEqual(missing["expected"]["onset"], 3)
        self.assertIsNone(missing["observed"])
        self.assertEqual(missing["kind"], "missing")
        self.assertEqual(result["pitch_matches"], 0)

    def test_unmatched_pitch_is_retained_and_boundary_pair_not_lost(self):
        result = build_comparisons(self.reference, self.notes, self.alignment, self.findings)[0]
        self.assertEqual([n["pitch"] for n in result["detected_notes"]], [61, 72])
        self.assertEqual(result["extra_detections"][0]["confidence"], .4)
        self.assertIsNone(result["extra_detections"][0]["reference_id"])

    def test_partial_measure_is_not_presented_as_scored(self):
        self.alignment["measures"][0]["scored"] = False
        self.assertEqual(build_comparisons(self.reference, self.notes, self.alignment, self.findings), [])


if __name__ == "__main__":
    unittest.main()
