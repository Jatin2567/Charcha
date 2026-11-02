"""Offline evidence import tests; no speech, model, credentials or ledger use."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("hindi_tamil_evidence_importer", ROOT / "scripts/import_hindi_tamil_evidence.py")
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


def report():
    contract = check.CONTRACT
    plan = contract.build_plan(endpoint="https://test-only.modal.run/v1", flow_id="00000000-0000-0000-0000-000000000001")
    cases = []
    for identifier, source, target, text in contract.CASES:
        cases.append({"case_id": identifier, "source_language": source, "target_language": target,
                      "source_text": text, "recognized_text": text, "translated_text": "test translation",
                      "status": check.COMPLETE, "meaning_review": "pending",
                      "source_preparation": {"first_pcm_ms": 10, "complete_ms": 20, "audio_seconds": 1.2},
                      "stt_final_ms": 100, "mt_complete_ms": 50,
                      "target_synthesis": {"first_pcm_ms": 30, "complete_ms": 60, "audio_seconds": 1.1},
                      "stt_start_to_target_first_pcm_ms": 180, "stt_start_to_target_complete_ms": 210})
    used = dict(stt_seconds=6, stt_connections=2, mt_requests=2,
                mt_characters=sum(len(row[3]) for row in contract.CASES), tts_requests=4,
                tts_characters=sum(len(row[3]) + len("test translation") for row in contract.CASES), voice_enrollments=0)
    return {"schema_version": 1, "record_type": "hindi_tamil_provider_chain_result", "plan": plan,
            "created_at": "2026-10-30T10:00:00+00:00", "status": check.COMPLETE,
            "cases": cases, "error_stage": None, "used": used, "wall_seconds": 1.23,
            "programme_credits_used": None, "actual_provider_charge_inr": None, "actual_modal_charge_usd": None,
            "meaning_review": "pending_human_bilingual_review", "listener_latency_ms": None,
            "rtc_tested": False, "physical_microphone_tested": False, "voice_cloning": False,
            "screening_mode": "off", "automatic_retries": 0, "cleanup_errors": [], "flow_status": "closed"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: pytest.fail("Offline importer attempted network access"))


def test_curates_exact_units_and_reference_without_exporting_source_content_or_private_state():
    value = report()
    value.update(api_key="DO-NOT-EXPORT", endpoint="https://private.example", flow_id="private-flow", balance=5000)
    value["cases"][0]["audio_file"] = "private.wav"
    public = check.curate(value, source_sha256="1" * 64)
    serialized = json.dumps(public, ensure_ascii=False)
    assert public["used"] == value["used"] and public["caps"] == check.CONTRACT.BUDGETS
    assert public["cost_reference"]["local_usage_reference_inr"] == round(6 * 27 / 3600 + value["used"]["tts_characters"] * 27 / 10000, 6)
    assert public["cost_reference"]["actual_provider_charge_inr"] is None
    assert public["listener_latency_ms"] is None and public["rtc_tested"] is False
    assert public["cases"][0]["source_preparation"]["complete_ms"] == 20
    assert public["cases"][0]["stt_start_to_target_first_pcm_ms"] == 180
    for forbidden in ("source_text", "recognized_text", "translated_text", "api_key", "endpoint", "flow_id", "balance", "audio_file", "DO-NOT-EXPORT", "private.wav", "test translation"):
        assert forbidden not in serialized
    assert not any("p95" in key or "p50" in key for key in public)


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(record_type="hindi_tamil_provider_chain_plan"),
    lambda r: r.update(rtc_tested=True), lambda r: r.update(physical_microphone_tested=True),
    lambda r: r.update(voice_cloning=True), lambda r: r.update(screening_mode="enforce"),
    lambda r: r.update(automatic_retries=1), lambda r: r.update(listener_latency_ms=200),
    lambda r: r.update(meaning_review="approved"), lambda r: r.update(actual_provider_charge_inr=1),
    lambda r: r.update(created_at="invalid"), lambda r: r.update(created_at="2026-10-30T10:00:00"),
    lambda r: r["used"].update(stt_seconds=31), lambda r: r["used"].update(stt_connections=True),
    lambda r: r["used"].update(voice_enrollments=1), lambda r: r["used"].update(tts_characters=801),
    lambda r: r["used"].update(stt_seconds=0), lambda r: r["used"].update(mt_characters=1),
    lambda r: r["cases"][0].update(stt_final_ms=float("nan")),
    lambda r: r["cases"][0].update(stt_final_ms=-1),
    lambda r: r["cases"][0].update(stt_final_ms=1232),
    lambda r: r["cases"][0].update(source_text="different test"),
    lambda r: r["cases"][0].update(source_language="bn"),
    lambda r: r["cases"][0].update(target_synthesis=None),
    lambda r: r["cases"][0]["source_preparation"].update(audio_seconds=8.1),
    lambda r: r["cases"][0]["target_synthesis"].update(first_pcm_ms=70),
    lambda r: r.update(cleanup_errors=["private-error-text"]),
    lambda r: r.update(cleanup_errors=["flow_close_failed"]),
])
def test_rejects_unreviewed_scope_or_inconsistent_measurements(mutation):
    value = report()
    mutation(value)
    with pytest.raises(check.Rejected):
        check.curate(value, source_sha256="1" * 64)


@pytest.mark.parametrize("field,changed", [("budgets", {**check.CONTRACT.BUDGETS, "tts_characters": 900}), ("voice_cloning", True), ("automatic_retries", 1), ("screening_mode", "monitor")])
def test_even_rehashed_plan_changes_cannot_expand_the_known_contract(field, changed):
    value = report()
    value["plan"][field] = changed
    value["plan"]["plan_sha256"] = check.CONTRACT.digest({key: val for key, val in value["plan"].items() if key != "plan_sha256"})
    with pytest.raises(check.Rejected, match="reviewed"):
        check.curate(value, source_sha256="1" * 64)


def test_partial_failure_keeps_unattempted_case_and_unknown_usage_visible():
    value = report()
    value.update(status="stopped_no_retry", error_stage="source_tts", used=None, cleanup_errors=["flow_close_failed"])
    value["cases"] = [{"case_id": row[0], "source_language": row[1], "target_language": row[2], "source_text": row[3], "status": "error" if index == 0 else "unattempted", "meaning_review": "pending"} for index, row in enumerate(check.CONTRACT.CASES)]
    public = check.curate(value, source_sha256="2" * 64)
    assert public["used"] is None and public["cleanup_complete"] is False
    assert public["cases"][1]["status"] == "unattempted"
    assert public["cost_reference"]["local_usage_reference_inr"] is None


def test_import_binds_original_bytes_and_replaces_only_the_explicit_null_placeholder(tmp_path, capsys):
    source, output = tmp_path / "report.json", tmp_path / "public.json"
    raw = json.dumps(report(), ensure_ascii=False).encode("utf-8")
    source.write_bytes(raw)
    output.write_text("null\n")
    assert check.main(["--input", str(source), "--output", str(output)]) == 0
    saved = json.loads(output.read_text())
    assert saved["source_report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert saved["record_type"] == check.TYPE
    assert "provider_calls_made_by_importer" in capsys.readouterr().out
    assert check.import_file(source, output) == saved  # Idempotent, unchanged import.
    changed = deepcopy(report())
    changed["wall_seconds"] = 2
    source.write_text(json.dumps(changed))
    with pytest.raises(check.Rejected, match="Prior evidence"):
        check.import_file(source, output)
    assert check.import_file(source, output, replace=True)["wall_seconds"] == 2


def test_invalid_import_has_no_output_and_does_not_echo_private_source(tmp_path, capsys):
    source, output = tmp_path / "report.json", tmp_path / "public.json"
    source.write_text('{"api_key":"NEVER-ECHO-THIS"}')
    assert check.main(["--input", str(source), "--output", str(output)]) == 2
    captured = capsys.readouterr()
    assert "NEVER-ECHO-THIS" not in captured.out + captured.err
    assert not output.exists()


@pytest.mark.parametrize("raw", [b'{"duplicate":1,"duplicate":2}', b'{"number":NaN}', b'x' * 1_048_577], ids=['duplicate-keys', 'nonfinite', 'oversized'])
def test_rejects_ambiguous_or_oversized_json(raw):
    with pytest.raises(check.Rejected):
        check.decode(raw)
