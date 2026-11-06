import builtins
import copy
import csv
import importlib.util
import io
import json
import os
import socket
import sqlite3
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "plan_five_language_test.py"
spec = importlib.util.spec_from_file_location("five_language_plan", MODULE_PATH)
planner = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(ROOT / "scripts"))
try:
    spec.loader.exec_module(planner)
finally:
    sys.path.pop(0)


def test_five_languages_cover_every_directed_pair_with_three_bounded_observations():
    plan = planner.build_plan()
    codes = ("hi", "ta", "bn", "te", "mr")
    assert tuple(plan["language_codes"]) == codes
    observed = [(route["source_language"], route["target_language"]) for route in plan["routes"]]
    assert set(observed) == {(source, target) for source in codes for target in codes if source != target}
    assert len(observed) == len(set(observed)) == plan["planned_directed_pairs"] == 20
    assert len(plan["trials"]) == plan["planned_observations"] == 60
    assert len({trial["trial_id"] for trial in plan["trials"]}) == 60
    assert set(Counter(trial["route_id"] for trial in plan["trials"]).values()) == {3}
    for route in plan["routes"]:
        trials = [trial for trial in plan["trials"] if trial["route_id"] == route["route_id"]]
        assert tuple(trial["planned_setup"] for trial in trials) == planner.REPEATS
        assert all(trial["participants"] == 2 and trial["microphone_speakers_at_once"] == 1 for trial in trials)
        assert all(trial["listener_microphone"] == "muted" for trial in trials)


def test_source_prompts_meanings_and_target_standard_voices_reuse_the_existing_draft_catalog():
    plan = planner.build_plan()
    voices = {entry[0]: entry[3] for entry in planner.LANGUAGES}
    for route in plan["routes"]:
        focus, prompt, meaning = planner.CASES[route["source_language"]]
        assert route["source_text"] == prompt
        assert route["source_characters"] == len(prompt) < 500
        assert route["review_focus"] == focus
        assert route["expected_meaning"] == list(meaning)
        assert route["source_reference_status"] == "unreviewed_draft"
        assert route["target_reference"] is None and route["semantic_result"] == "not_tested"
        assert route["voice"] == {"mode": "standard", "model": "timbre-v2.5", "name": voices[route["target_language"]]}


def test_every_proposal_requires_its_own_approval_and_has_no_results_retries_or_cloning():
    plan = planner.build_plan()
    assert plan["plan_only"] and plan["voice_cloning_deferred"]
    assert plan["provider_calls_made"] == plan["gpu_resources_started"] == plan["completed_observations"] == 0
    assert not plan["approval_granted"] and not plan["full_matrix_authorized"] and not plan["automatic_matrix_runner"]
    assert plan["results_status"] == "not_run"
    for trial in plan["trials"]:
        assert trial["stage"] == "latency" and trial["screening_mode"] == "off"
        assert trial["input_kind"] == "audio" and trial["voice_mode"] == "standard"
        assert trial["review_status"] == "pending" and trial["observed_setup_state"] is None
        assert all(value is None for value in trial["measurements"].values())
        flow = trial["proposed_flow"]
        assert flow["approval_granted"] is False and flow["automatic_retries"] == 0
        assert flow["renewal_requires_new_approval"] and flow["stt_budget_includes_handshake_and_idle"]
        assert flow["expiry_seconds"] == 120
        assert flow["budgets"] == {
            "stt_seconds": 15, "stt_connections": 1,
            "mt_requests": 1, "mt_characters": 500,
            "tts_requests": 1, "tts_characters": 300, "voice_enrollments": 0,
        }


def test_aggregate_reference_is_exact_and_separate_from_gcp_stage_and_project_caps():
    plan = planner.build_plan()
    budget = plan["budget"]
    assert budget["max_stt_seconds"] == 900 and budget["max_tts_characters"] == 18000
    assert budget["max_stt_connections"] == budget["max_mt_requests"] == budget["max_tts_requests"] == 60
    assert budget["max_mt_source_characters"] == 30000
    assert Decimal(budget["stt_reference_inr"]) == Decimal("6.75")
    assert Decimal(budget["tts_reference_inr"]) == Decimal("48.60")
    assert Decimal(budget["speech_reference_inr"]) == Decimal("55.35")
    assert budget["gcp_latency_stage_ceiling_inr"] == budget["gcp_reserved_for_later_inr"] == 2500
    assert budget["gcp_project_ceiling_inr"] == 5000
    assert budget["actual_gnani_billed_inr"] is budget["actual_gcp_spend_inr"] is None
    assert budget["gcp_price_and_runtime_estimate"] is budget["programme_credit_conversion"] is None
    assert budget["reference_is_invoice_or_grant"] is False
    assert budget["gnani_each_flow_requires_approval"] and budget["gcp_budget_is_not_a_provider_flow_grant"]


def test_every_prompt_setting_limit_and_reference_is_bound_by_deterministic_hashes():
    plan = planner.build_plan()
    assert plan == planner.build_plan()
    for route in plan["routes"]:
        assert route["route_sha256"] == planner.content_hash({k: v for k, v in route.items() if k != "route_sha256"})
    for trial in plan["trials"]:
        assert trial["trial_sha256"] == planner.content_hash({k: v for k, v in trial.items() if k != "trial_sha256"})
        assert trial["route_sha256"] == next(route["route_sha256"] for route in plan["routes"] if route["route_id"] == trial["route_id"])
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    assert plan["plan_sha256"] == planner.content_hash(body)
    for mutate in (
        lambda p: p["routes"][0].update(source_text="different draft"),
        lambda p: p["trials"][0]["proposed_flow"]["budgets"].update(stt_seconds=16),
        lambda p: p["trials"][0].update(screening_mode="enforce"),
        lambda p: p["budget"].update(gcp_latency_stage_ceiling_inr=3000),
    ):
        changed = copy.deepcopy(body)
        mutate(changed)
        assert planner.content_hash(changed) != plan["plan_sha256"]
    fresh = planner.build_plan()
    plan["trials"][0]["proposed_flow"]["budgets"]["stt_seconds"] = 999
    plan["routes"][0]["expected_meaning"].append("changed")
    assert plan["trials"][1]["proposed_flow"]["budgets"]["stt_seconds"] == 15
    assert planner.build_plan() == fresh


def test_blank_csv_retains_all_trial_ids_but_never_invents_measurements_or_reviews():
    plan = planner.build_plan()
    rows = list(csv.DictReader(io.StringIO(planner.review_csv(plan))))
    assert len(rows) == 60
    assert {row["trial_id"] for row in rows} == {trial["trial_id"] for trial in plan["trials"]}
    assert all(row["review_status"] == "pending" and row["approval_granted"] == "false" for row in rows)
    assert all(row["plan_sha256"] == plan["plan_sha256"] for row in rows)
    assert all(row[field] == "" for row in rows for field in planner.RESULT_FIELDS)
    assert rows[0]["source_draft"] == planner.CASES["hi"][1]
    assert "stt_processing_to_transcript_ms" in rows[0]
    assert "listener_common_clock_evidence_id" in rows[0]


@pytest.mark.parametrize("text", ["=1+1", "+cmd", "-2+3", "@formula", "  =1", "\tvalue", "\rvalue", "\nvalue"])
def test_review_csv_escapes_spreadsheet_formula_prefixes(text):
    assert planner.csv_safe(text).startswith("'")


def test_checked_in_plan_matches_generator_exactly():
    saved = json.loads((ROOT / "web" / "src" / "data" / "fiveLanguagePlan.json").read_text(encoding="utf-8"))
    assert saved == planner.build_plan()


def test_cli_is_offline_with_environment_files_network_and_ledger_forbidden(monkeypatch, capsys):
    source = MODULE_PATH.read_text(encoding="utf-8")
    original_import = builtins.__import__

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Five-language planner must stay offline")

    def restricted_import(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"charcha", "dotenv", "httpx", "requests", "websockets", "socket", "sqlite3", "pydantic_settings", "subprocess"}:
            raise AssertionError("No provider, cloud, settings or ledger imports")
        return original_import(name, *args, **kwargs)

    class ForbiddenEnvironment(dict):
        __getitem__ = get = __iter__ = forbidden

    with monkeypatch.context() as context:
        context.setattr(os, "environ", ForbiddenEnvironment())
        context.setattr(builtins, "open", forbidden)
        context.setattr(builtins, "__import__", restricted_import)
        context.setattr(Path, "read_text", forbidden)
        context.setattr(Path, "open", forbidden)
        context.setattr(socket, "socket", forbidden)
        context.setattr(sqlite3, "connect", forbidden)
        namespace = {"__name__": "offline_five_language_test"}
        exec(compile(source, str(MODULE_PATH), "exec"), namespace)
        assert namespace["main"]([]) == 0
        assert len(list(csv.DictReader(io.StringIO(namespace["review_csv"]())))) == 60
    output = capsys.readouterr().out
    assert output.isascii() and json.loads(output)["planned_observations"] == 60


@pytest.mark.parametrize("arguments", [["--run"], ["--execute"], ["--approve"], ["--renew"], ["--plan", "--run"]])
def test_cli_rejects_execution_and_approval(arguments, capsys):
    assert planner.main(arguments) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "cannot run, approve or renew" in captured.err
