"""Recompute both audio examples and compare the controlled result to separate truth."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from piano_review.pipeline import run_analysis, write_json
from piano_review.controlled import verify_controlled_report

if __name__ == "__main__":
    real = run_analysis("real")
    controlled = run_analysis("controlled")
    truth = json.loads((ROOT / "data/controlled-truth.json").read_text(encoding="utf-8"))
    verification = verify_controlled_report(controlled, truth)
    verification["checks"].extend([
        {"name": "real_original_measure_numbers", "passed": real["scoring"]["scored_measures"] == list(range(1, 12))},
        {"name": "controlled_two_confirmed_errors", "passed": controlled["summary"]["error_count"] == 2},
        {"name": "controlled_no_other_findings", "passed": controlled["summary"]["uncertain_count"] == 0},
        {"name": "real_all_176_pairs_exposed", "passed": sum(len(m["events"]) for m in real["comparisons"]) == 176
         and sum(m["pitch_matches"] for m in real["comparisons"]) == 176},
        {"name": "controlled_all_48_pairs_exposed", "passed": sum(len(m["events"]) for m in controlled["comparisons"]) == 48},
        {"name": "same_decoder_and_schema", "passed": all(r["schema_version"] == 2 and r["decoder"]["name"] == "candidate"
         for r in (real, controlled))},
    ])
    verification["passed"] = all(check["passed"] for check in verification["checks"])
    write_json(ROOT / "reports/controlled-verification.json", verification)
    print(json.dumps(verification, indent=2))
    raise SystemExit(0 if verification["passed"] else 1)
