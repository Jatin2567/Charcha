import builtins
import importlib.util
import json
import os
import socket
import sqlite3
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "plan_language_matrix.py"
spec = importlib.util.spec_from_file_location("language_matrix_plan", MODULE_PATH)
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)


def test_matrix_covers_every_cross_language_pair_once_without_self_routes():
    plan = matrix.build_plan()
    codes = {language["code"] for language in plan["languages"]}
    observed = [(route["source_language"], route["target_language"]) for route in plan["routes"]]
    assert set(observed) == {(source, target) for source in codes for target in codes if source != target}
    assert len(observed) == len(set(observed)) == plan["planned_directed_pairs"] == 90
    assert plan["baseline_directed_pairs"] == 12
    assert sum(route["first_phase"] == "baseline_four" for route in plan["routes"]) == 12
    assert plan["simultaneous_user_count_required"] == 2


def test_each_route_is_an_unapproved_bounded_standard_voice_flow_not_a_bulk_grant():
    plan = matrix.build_plan()
    voices = {entry["code"]: entry["standard_voice"] for entry in plan["languages"]}
    assert not plan["approval_granted"] and not plan["full_matrix_authorized"] and not plan["automatic_matrix_runner"]
    assert plan["provider_calls_made"] == 0
    assert "or" not in voices and len(voices) == 10
    for route in plan["routes"]:
        flow = route["proposed_individual_typed_flow"]
        assert flow["budgets"] == {
            "stt_seconds": 0, "stt_connections": 0,
            "mt_requests": 1, "mt_characters": len(route["source_text"]),
            "tts_requests": 1, "tts_characters": 200, "voice_enrollments": 0,
        }
        assert flow["approval_granted"] is False and flow["automatic_retries"] == 0
        assert flow["expiry_seconds"] == 120
        assert flow["evon_charge"] is None and flow["actual_billed_total"] is None
        assert route["voice"] == {"mode": "standard", "model": "timbre-v2.5", "name": voices[route["target_language"]]}
        assert route["source_reference_status"] == "unreviewed_draft"
        assert route["target_reference"] is None and route["semantic_result"] == "not_tested"


def test_fanout_counts_languages_not_listeners_and_preserves_free_original_audio_path():
    mixed = matrix.speaker_flow("hi", ["ta", "ta", "bn", "hi"])
    assert mixed["stt_connections_while_unmuted"] == 1
    assert mixed["different_target_languages"] == ["bn", "ta"]
    assert mixed["mt_jobs_per_utterance"] == mixed["tts_jobs_per_utterance"] == 2
    assert mixed["same_language_original_forwarding"] is True and mixed["self_output"] is False
    same = matrix.speaker_flow("hi", ["hi", "hi"])
    assert same["stt_connections_while_unmuted"] == same["mt_jobs_per_utterance"] == same["tts_jobs_per_utterance"] == 0
    assert matrix.speaker_flow("hi", [])["same_language_original_forwarding"] is False
    with pytest.raises(ValueError):
        matrix.speaker_flow("or", ["hi"])


def test_hashes_bind_drafts_and_each_result_is_independent():
    plan = matrix.build_plan()
    for route in plan["routes"]:
        body = {key: value for key, value in route.items() if key != "route_sha256"}
        assert route["route_sha256"] == matrix.content_hash(body)
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    assert plan["plan_sha256"] == matrix.content_hash(body)
    fresh = matrix.build_plan()
    plan["routes"][0]["expected_meaning"].append("unreviewed change")
    assert matrix.build_plan() == fresh


def test_fresh_plan_cli_cannot_read_environment_files_or_construct_provider_network_or_ledger(monkeypatch, capsys):
    source = MODULE_PATH.read_text(encoding="utf-8")
    original_import = builtins.__import__

    def forbidden(*_args, **_kwargs):
        raise AssertionError("The matrix plan is offline only")

    def restricted_import(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"artha_mesh", "dotenv", "httpx", "websockets", "socket", "sqlite3", "pydantic_settings"}:
            raise AssertionError("The matrix plan cannot import application/provider clients")
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
        namespace = {"__name__": "offline_matrix_test"}
        exec(compile(source, str(MODULE_PATH), "exec"), namespace)
        assert namespace["main"]([]) == 0
    output = capsys.readouterr().out
    assert output.isascii()
    assert json.loads(output)["planned_directed_pairs"] == 90


@pytest.mark.parametrize("arguments", [["--run"], ["--approve"], ["--renew"]])
def test_cli_rejects_execution_or_approval(arguments, capsys):
    assert matrix.main(arguments) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "cannot run, approve or renew" in captured.err
