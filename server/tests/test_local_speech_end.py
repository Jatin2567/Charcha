"""Synthetic timing-fixture safeguards; no RTC, providers, camera or microphone."""
import builtins
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import struct

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/measure_local_speech_end.py"
spec = importlib.util.spec_from_file_location("local_speech_end_fixture_test", MODULE_PATH)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def result():
    return {"schema_version": 1, "record_type": "speech_end_latency_evidence", "recorded_on": "2026-10-30",
        "evidence_kind": "synthetic_local_rtc", "clock": "single_process_monotonic",
        "boundary": "source_end_to_first_decoded_rtc", "source_end_reference": "last_voiced_source_frame_playout",
        "physical_playback_measured": False, "provider_calls": 0, "screening_mode": "off", "voice_cloning": False,
        "target_ms": 2000, "acceptance": "not_verified", "samples": [
            {"trial_id": "test-first", "condition": "first_route", "source_language": "hi", "target_language": "ta",
             "status": "complete", "source_end_to_decoded_ms": -100,
             "source_end_to_render_estimate_ms": None, "source_end_to_physical_playback_ms": None},
            {"trial_id": "test-warm", "condition": "warm_route", "source_language": "hi", "target_language": "ta",
             "status": "timeout", "source_end_to_decoded_ms": None,
             "source_end_to_render_estimate_ms": None, "source_end_to_physical_playback_ms": None}],
        "summary": {"attempted": 2, "completed": 1, "failed": 1, "p50_decoded_ms": -100, "p95_decoded_ms": -100},
        "limitations": ["private upstream detail should be replaced"]}


def test_import_and_plan_never_read_environment_files_or_construct_settings_sdk_network_or_ledger(monkeypatch):
    source = MODULE_PATH.read_text(encoding="utf-8")
    original_import = builtins.__import__
    def forbidden(*_a, **_k): pytest.fail("Offline planning attempted runtime work")
    def restricted_import(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"artha_mesh", "livekit", "httpx", "websockets", "dotenv", "pydantic_settings"}:
            forbidden()
        return original_import(name, *args, **kwargs)
    class NoEnvironment(dict):
        __getitem__ = get = __iter__ = items = keys = forbidden
    with monkeypatch.context() as context:
        context.setattr(os, "environ", NoEnvironment())
        context.setattr(builtins, "open", forbidden)
        context.setattr(Path, "open", forbidden)
        context.setattr(Path, "read_text", forbidden)
        context.setattr(socket, "socket", forbidden)
        context.setattr(sqlite3, "connect", forbidden)
        context.setattr(builtins, "__import__", restricted_import)
        namespace = {"__name__": "local_fixture_offline_only", "__file__": str(MODULE_PATH)}
        exec(compile(source, str(MODULE_PATH), "exec"), namespace)
        plan = namespace["plan"]()
    assert plan["plan_only"] and plan["provider_calls"] == 0
    assert plan["conditions"] == {"first_route": 1, "warm_route": 10}
    assert plan["physical_playback_measured"] is False and plan["acceptance"] == "not_verified"
    assert plan["boundary"] == "source_end_to_first_decoded_rtc"


def test_default_cli_prints_only_plan_without_loading_app_configuration_or_running_fixture(monkeypatch, capsys):
    def forbidden(*_a, **_k): pytest.fail("Default CLI performed runtime work")
    monkeypatch.setattr(check, "run_local", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    assert check.main([]) == 0
    assert json.loads(capsys.readouterr().out)["record_type"] == "local_speech_end_latency_plan"


@pytest.mark.parametrize("values,fraction,expected", [([], .5, None), ([-100], .95, -100),
    ([300, -100, 80], .5, 80), ([300, -100, 80], .95, 300),
    ([100] * 9 + [2000], .95, 2000), ([-300, -200, -100], .5, -200)])
def test_nearest_rank_preserves_signed_offsets_and_unknown_empty_samples(values, fraction, expected):
    original = values.copy()
    assert check.percentile(values, fraction) == expected
    assert values == original


async def test_fixture_initial_silence_never_becomes_a_transcript_and_each_600ms_gap_finalizes_once():
    fixture = check.Fixture()
    quiet = bytes(320 * 2)
    voiced = struct.pack("<320h", *([4000] * 320))
    # 800ms startup silence must not finalize anything; then two synthetic turns.
    chunks = [quiet] * 40 + [voiced] * 30 + [quiet] * 30 + [quiet] * 20 + [voiced] * 30 + [quiet] * 30 + [quiet] * 40
    sent, boundaries, processing = [], [], []
    async def audio():
        for index, chunk in enumerate(chunks):
            sent.append(index)
            yield chunk
    rows = []
    async for row in fixture.transcribe(audio(), "hi", on_processing=lambda: processing.append(True)):
        rows.append(row)
        boundaries.append(len(sent))
    assert fixture.ready.is_set() and fixture.recognitions == 2
    assert boundaries == [100, 180]
    assert [row.segment_id for row in rows] == ["1", "2"] and len(processing) == 2
    assert all(row.stt_ms == 0 and row.text.startswith("Synthetic source trial") for row in rows)


async def test_provider_doubles_keep_fixed_delays_short_first_chunk_and_no_voice_cloning(monkeypatch):
    delays = []
    async def synthetic_sleep(seconds): delays.append(seconds)
    monkeypatch.setattr(check.asyncio, "sleep", synthetic_sleep)
    fixture = check.Fixture()
    assert await fixture.translate("synthetic source", "hi", "ta") == "Synthetic target fixture"
    chunks = [chunk async for chunk in fixture.synthesize("synthetic target", "ta", None)]
    assert delays == [.1, .05]
    assert len(chunks[0]) == 240 * 2 and sum(map(len, chunks)) == 4800 * 2
    assert all(isinstance(chunk, bytes) and len(chunk) % 2 == 0 for chunk in chunks)
    assert fixture.translations == fixture.syntheses == 1 and any(b"".join(chunks))


def test_curated_export_reconstructs_nested_allowlists_and_fixed_limitations():
    raw = result()
    raw.update(api_key="NEVER-EXPORT-KEY", endpoint="https://private.example", balance=5000,
               local_stack=[{"file": "C:/private/local/file.py"}], fixture_error="private-provider-body")
    raw["samples"][0].update(private_pcm="NEVER-EXPORT-AUDIO", flow_id="NEVER-EXPORT-FLOW",
                             transcript="NEVER-EXPORT-TEXT")
    raw["summary"]["private_ledger"] = "NEVER-EXPORT-LEDGER"
    raw["limitations"] = ["NEVER-EXPORT-UPSTREAM-ERROR"]
    public = check.curate_result(raw, "a" * 64)
    encoded = json.dumps(public)
    for private in ("NEVER-EXPORT", "api_key", "endpoint", "balance", "local_stack", "fixture_error", "private_pcm", "flow_id", "transcript", "private_ledger"):
        assert private not in encoded
    assert set(public["samples"][0]) == {"trial_id", "condition", "source_language", "target_language", "status",
        "source_end_to_decoded_ms", "source_end_to_render_estimate_ms", "source_end_to_physical_playback_ms"}
    assert set(public["summary"]) == {"attempted", "completed", "failed", "p50_decoded_ms", "p95_decoded_ms"}
    assert public["source_report_sha256"] == "a" * 64
    assert public["samples"][0]["source_end_to_decoded_ms"] == -100
    assert public["samples"][1]["source_end_to_decoded_ms"] is None
    assert public["physical_playback_measured"] is False and public["acceptance"] == "not_verified"
    assert public["summary"]["failed"] == 1


def test_curated_mutations_do_not_change_original_measurements():
    raw = result()
    before = deepcopy(raw)
    public = check.curate_result(raw, "b" * 64)
    public["samples"][0]["source_end_to_decoded_ms"] = 999
    public["summary"]["p50_decoded_ms"] = 999
    public["limitations"].append("public-only edit")
    assert raw == before


def test_mocked_cli_binds_written_raw_bytes_even_when_text_output_uses_crlf(tmp_path, monkeypatch, capsys):
    source = tmp_path / "work/local-result.json"
    public_path = tmp_path / "web/src/data/speechEndLatencyResults.json"
    public_path.parent.mkdir(parents=True)
    monkeypatch.setattr(check, "ROOT", tmp_path)
    raw_result = result()
    raw_result["samples"] = [{**deepcopy(raw_result["samples"][0]), "trial_id": f"mock-{index}",
        "condition": "first_route" if index == 0 else "warm_route", "source_end_to_decoded_ms": 800}
        for index in range(11)]
    raw_result.update(summary={"attempted": 11, "completed": 11, "failed": 0,
        "p50_decoded_ms": 800, "p95_decoded_ms": 800}, fixture_error=None, cleanup_errors=[])
    async def local_result_without_rtc():
        return deepcopy(raw_result)
    monkeypatch.setattr(check, "run_local", local_result_without_rtc)
    original_open = Path.open
    def windows_text_open(path, mode="r", *args, **kwargs):
        if path == source and mode == "x":
            kwargs["newline"] = "\r\n"
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", windows_text_open)
    assert check.main(["--run-local", "--output", str(source), "--curated-output", str(public_path)]) == 0
    raw_bytes = source.read_bytes()
    assert b"\r\n" in raw_bytes
    public = json.loads(public_path.read_text(encoding="utf-8"))
    assert public["source_report_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert public == check.curate_result(raw_result, hashlib.sha256(raw_bytes).hexdigest())
    assert public["provider_calls"] == 0 and public["acceptance"] == "not_verified"
    assert "provider" not in capsys.readouterr().err


def test_saved_actual_raw_and_public_source_hash_agree_when_local_artifact_is_available():
    source = ROOT / "work/local/speech-end-rtc-cooperative-20261030.json"
    public_path = ROOT / "web/src/data/speechEndLatencyResults.json"
    if not source.is_file() or not public_path.is_file():
        pytest.skip("Saved local RTC evidence is optional outside the operator workspace")
    raw_bytes = source.read_bytes()
    raw, public = json.loads(raw_bytes), json.loads(public_path.read_text(encoding="utf-8"))
    assert public == check.curate_result(raw, hashlib.sha256(raw_bytes).hexdigest())
    assert raw["summary"] == public["summary"]
    assert len(public["samples"]) == 11 and sum(row["condition"] == "first_route" for row in public["samples"]) == 1
    warm = [row["source_end_to_decoded_ms"] for row in public["samples"] if row["condition"] == "warm_route" and row["status"] == "complete"]
    assert raw["warm_summary"]["p50_decoded_ms"] == check.percentile(warm, .5)
    assert raw["warm_summary"]["p95_decoded_ms"] == check.percentile(warm, .95)
    assert public["provider_calls"] == 0 and not public["physical_playback_measured"] and public["acceptance"] == "not_verified"
    assert all(row["source_end_to_physical_playback_ms"] is None for row in public["samples"])
