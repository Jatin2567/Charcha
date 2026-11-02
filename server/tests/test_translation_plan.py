import builtins
import importlib.util
import json
import os
import socket
import sqlite3
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "plan_translation_test.py"
spec = importlib.util.spec_from_file_location("translation_test_plan", MODULE_PATH)
plan_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan_module)


def test_plan_limits_match_exact_typed_source_and_keep_speech_and_cloning_off():
    plan = plan_module.build_plan()
    assert [case["source_characters"] for case in plan["cases"]] == [31, 49]
    assert plan["flow"]["budgets"] == {
        "stt_seconds": 0, "stt_connections": 0, "mt_requests": 2,
        "mt_characters": 80, "tts_requests": 2, "tts_characters": 400,
        "voice_enrollments": 0,
    }
    assert plan["flow"]["expiry_seconds"] == 120
    assert plan["flow"]["automatic_retries"] == 0
    assert plan["voice"]["mode"] == "standard"
    assert plan["voice"]["by_target_language"] == {"hi": "Nalini", "ta": "Trisha"}
    assert plan["input_kind"] == "text" and plan["microphones"] == "off_for_both_participants"
    assert plan["approval_granted"] is False
    assert plan["next_stage"]["approval_granted"] is False
    assert plan["next_stage"]["voice_cloning"] == "deferred"
    assert plan["cost_reference"]["actual_billed_total"] is None
    assert plan["cost_reference"]["evon_charge"] is None


def test_case_and_plan_hashes_bind_the_reviewed_content_without_mutable_shared_state():
    first = plan_module.build_plan()
    second = plan_module.build_plan()
    assert first == second
    assert len({case["case_id"] for case in first["cases"]}) == 2
    for case in first["cases"]:
        reviewed = {key: value for key, value in case.items() if key != "case_sha256"}
        assert case["case_sha256"] == plan_module.content_hash(reviewed)
        reviewed["source_text"] += " changed"
        assert case["case_sha256"] != plan_module.content_hash(reviewed)
    manifest = {key: value for key, value in first.items() if key != "plan_sha256"}
    assert first["plan_sha256"] == plan_module.content_hash(manifest)
    first["cases"][0]["expected_meaning"].append("unreviewed mutation")
    assert plan_module.build_plan() == second


def test_fresh_script_and_cli_do_not_read_environment_files_or_construct_network_or_ledger(monkeypatch, capsys):
    source = MODULE_PATH.read_text(encoding="utf-8")
    original_import = builtins.__import__

    def forbidden(*_args, **_kwargs):
        raise AssertionError("The offline plan must not access files, environment, network or ledger")

    def restricted_import(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"artha_mesh", "dotenv", "httpx", "websockets", "socket", "sqlite3", "pydantic_settings"}:
            raise AssertionError("The offline plan must not import application/provider clients")
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
        namespace = {"__name__": "offline_translation_plan_test"}
        exec(compile(source, str(MODULE_PATH), "exec"), namespace)
        assert namespace["main"]([]) == 0
    output = capsys.readouterr().out
    assert output.isascii()
    decoded = json.loads(output)
    assert decoded["provider_calls_made"] == 0
    assert decoded["cases"][0]["source_text"] == plan_module.CASES[0][3]


@pytest.mark.parametrize("arguments", [["--run"], ["--approve"], ["--flow-id", "anything"]])
def test_cli_rejects_run_or_approval_actions(arguments, capsys):
    assert plan_module.main(arguments) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "cannot run or approve" in output.err
