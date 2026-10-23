import argparse
import csv
import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "run.py"
spec = importlib.util.spec_from_file_location("evaluation_runner", MODULE_PATH)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def test_numeric_surface_check_normalizes_native_digits_but_never_calls_it_accuracy():
    case = {"critical_values": {"numeric": ["25000", "10"]}}
    assert evaluation.number_surface_check(case, "₹२५,००० এবং ১০") == "present_unverified"
    assert evaluation.number_surface_check(case, "₹२५,००० এবং ১১") == "review_needed"


def test_report_excludes_demo_and_failed_timings_and_requires_bilingual_rater(tmp_path):
    dataset = tmp_path / "cases.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    ratings = tmp_path / "ratings.csv"
    dataset.write_text("\n".join(json.dumps({
        "id": case_id, "source_text": "50 cartons", "reference_draft": "draft",
        "reference_status": "unreviewed_draft", "critical_values": {"numeric": ["50"]},
    }) for case_id in ("live", "demo", "failed")), encoding="utf-8")
    predictions.write_text("\n".join(json.dumps(row) for row in [
        {"case_id": "live", "mode": "live", "status": "complete", "translation": "50 boxes", "server_pipeline_ms": 900, "measurement": "server_pipeline"},
        {"case_id": "demo", "mode": "demo", "status": "complete", "translation": "50 boxes", "server_pipeline_ms": 1, "measurement": "server_pipeline"},
        {"case_id": "failed", "mode": "live", "status": "error", "translation": "", "server_pipeline_ms": 5, "measurement": "server_pipeline"},
    ]), encoding="utf-8")
    evaluation.write_csv(ratings, evaluation.RATING_COLUMNS, [
        {"case_id": "live", "reviewer_id": "qualified", "source_fluent": "yes", "target_fluent": "yes", "meaning_1_to_5": "4", "critical_values_correct": "no"},
        {"case_id": "live", "reviewer_id": "not-target-fluent", "source_fluent": "yes", "target_fluent": "no", "meaning_1_to_5": "5", "critical_values_correct": "yes"},
    ])
    output = tmp_path / "report"
    evaluation.report(argparse.Namespace(dataset=dataset, predictions=predictions, ratings=ratings, output_dir=output))
    summary = json.loads((output / "summary.json").read_text())
    assert summary["cases_attempted"] == 3
    assert summary["cases_completed"] == 2
    assert summary["live_server_timing_count"] == 1
    assert summary["live_server_pipeline_p95_ms"] == 900
    assert summary["cases_with_bilingual_ratings"] == 1
    with (output / "case_report.csv").open(encoding="utf-8-sig", newline="") as stream:
        live = list(csv.DictReader(stream))[0]
    assert live["bilingual_ratings"] == "1"
    assert live["mean_meaning_rating"] == "4.0"
    assert live["human_critical_pass"] == "False"


def test_dataset_has_unique_ids_and_is_explicitly_unreviewed():
    cases = evaluation.load_jsonl(evaluation.DEFAULT_DATASET)
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["source_language"] for case in cases} == {"hi", "ta", "bn"}
    assert all(case["reference_status"] == "unreviewed_draft" for case in cases)
    assert all(case["source_text"] and case["reference_draft"] for case in cases)
