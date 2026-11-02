"""Offline strict redaction tests for a separate single-flow follow-up record."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ta_hi_followup_evidence_test", ROOT / "scripts/import_tamil_hindi_followup_evidence.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def report():
    contract = check.CONTRACT
    recognized, translated = contract.SOURCE_TEXT, "मुझे नीली किताब चाहिए, लाल नहीं।"
    return {"schema_version": 1, "record_type": "tamil_hindi_followup_result",
        "plan": contract.build_plan(endpoint="https://test-only.modal.run/v1", flow_id="00000000-0000-0000-0000-000000000001"),
        "created_at": "2026-10-30T12:00:00+00:00", "status": check.COMPLETE,
        "error_stage": None, "error_class": None, "used": {"stt_seconds": 9, "stt_connections": 1,
            "mt_requests": 1, "mt_characters": len(recognized), "tts_requests": 1,
            "tts_characters": len(translated), "voice_enrollments": 0},
        "flow_status": "closed", "wall_seconds": 12.3, "programme_credits_used": None,
        "actual_provider_charge_inr": None, "actual_modal_charge_usd": None,
        "meaning_review": "pending_human_bilingual_review", "listener_latency_ms": None,
        "rtc_tested": False, "physical_microphone_tested": False, "voice_cloning": False,
        "screening_mode": "off", "automatic_retries": 0, "cleanup_errors": [], "source_tts_requests": 0,
        "stt": {"requested_model": "prisma-v3.0", "provider_model": None},
        "recognized_text": recognized, "translated_text": translated, "stt_final_ms": 9000,
        "mt_complete_ms": 1000, "target_synthesis": {"first_pcm_ms": 200, "complete_ms": 800, "audio_seconds": 2.4},
        "stt_start_to_target_first_pcm_ms": 10200, "stt_start_to_target_complete_ms": 10800}


@pytest.fixture(autouse=True)
def no_network_or_runtime(monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: pytest.fail("Importer attempted network access"))
    monkeypatch.setattr(check.CONTRACT.shared, "_runtime", lambda *_a, **_k: pytest.fail("Importer loaded runtime/settings"))
    monkeypatch.setattr(check.CONTRACT, "read_input", lambda *_a, **_k: pytest.fail("Importer accessed private source audio"))


def test_curated_schema_retains_only_fixed_provenance_units_timings_and_unknown_charges():
    value = report()
    value.update(api_key="NEVER-EXPORT-KEY", endpoint="https://private.example", flow_id="private-id", balance=5000,
                 audio_path="private-source.wav", programme_credits_used="private-credit-information")
    value["target_synthesis"]["private_audio"] = "NEVER-EXPORT-PCM"
    public = check.curate(value, source_sha256="1" * 64)
    assert public["record_type"] == "controlled_tamil_hindi_followup_evidence"
    assert public["input_sha256"] == check.CONTRACT.INPUT_SHA256 and public["source_audio_seconds"] == 3.2
    assert public["translation_model"] == check.CONTRACT.MODEL and public["prompt_version"] == check.CONTRACT.shared._prompt.PROMPT_VERSION
    assert public["stt"] == {"requested_model": "prisma-v3.0", "provider_model": None}
    assert public["used"] == value["used"] and public["caps"] == check.CONTRACT.BUDGETS
    assert public["timings"]["target_tts_first_pcm_ms"] == 200 and public["timings"]["stt_start_to_target_complete_ms"] == 10800
    assert public["flow_closed"] and public["cleanup_complete"] and public["meaning_review"] == "pending"
    assert public["listener_latency_ms"] is None and public["physical_microphone_tested"] is False
    cost = public["cost_reference"]
    assert cost["approved_maximum_reference_inr"] == .9975
    assert cost["local_usage_reference_inr"] == round(9 * 27 / 3600 + value["used"]["tts_characters"] * 27 / 10000, 6)
    assert cost["actual_provider_charge_inr"] is cost["actual_modal_charge_usd"] is cost["programme_credits_used"] is None
    encoded = json.dumps(public, ensure_ascii=False)
    for forbidden in ("NEVER-EXPORT", "source_text", "recognized_text", "translated_text", "api_key", "endpoint",
                      "flow_id", "balance", "audio_path", "private-source.wav", "private-id", "private-credit-information"):
        assert forbidden not in encoded
    assert value["recognized_text"] not in encoded and value["translated_text"] not in encoded
    assert "p95" not in encoded and "p50" not in encoded


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(record_type="hindi_tamil_provider_chain_result"),
    lambda r: r.update(record_type="tamil_hindi_followup_plan"), lambda r: r.update(schema_version=True),
    lambda r: r.update(status="unknown-private-status"), lambda r: r.update(error_class="private-provider-error"),
    lambda r: r.update(error_class={"private": "error"}), lambda r: r.update(error_stage=["stt"]),
    lambda r: r.update(rtc_tested=True), lambda r: r.update(physical_microphone_tested=True),
    lambda r: r.update(voice_cloning=True), lambda r: r.update(screening_mode="monitor"),
    lambda r: r.update(automatic_retries=1), lambda r: r.update(source_tts_requests=1),
    lambda r: r.update(listener_latency_ms=5), lambda r: r.update(meaning_review="approved"),
    lambda r: r.update(actual_provider_charge_inr=1), lambda r: r.update(actual_modal_charge_usd=1),
    lambda r: r.update(stt={"requested_model": "prisma-v2.5", "provider_model": None}),
    lambda r: r.update(stt={"requested_model": "prisma-v3.0", "provider_model": "prisma-v3.0"}),
    lambda r: r.update(created_at="invalid"), lambda r: r.update(created_at="2026-10-30T12:00:00"),
    lambda r: r.update(wall_seconds=float("nan")), lambda r: r.update(wall_seconds=-1),
    lambda r: r["used"].update(stt_seconds=26), lambda r: r["used"].update(stt_connections=True),
    lambda r: r["used"].update(stt_seconds=0), lambda r: r["used"].update(mt_requests=2),
    lambda r: r["used"].update(mt_characters=1), lambda r: r["used"].update(tts_characters=301),
    lambda r: r["used"].update(voice_enrollments=1), lambda r: r["used"].update(extra=1),
    lambda r: r.update(stt_final_ms=float("inf")), lambda r: r.update(stt_final_ms=12302),
    lambda r: r.update(stt_final_ms=None), lambda r: r.update(target_synthesis=None),
    lambda r: r.update(stt_start_to_target_first_pcm_ms=11000),
    lambda r: r["target_synthesis"].update(audio_seconds=15.1),
    lambda r: r["target_synthesis"].update(audio_seconds=0),
    lambda r: r["target_synthesis"].update(first_pcm_ms=900),
    lambda r: r.update(cleanup_errors=["private-error"]), lambda r: r.update(cleanup_errors=["flow_close_failed"]),
    lambda r: r.update(flow_status=None), lambda r: r.update(used=None),
    lambda r: r.update(recognized_text=""), lambda r: r.update(translated_text="अ" * 301),
])
def test_rejects_unreviewed_scope_invalid_metrics_or_inconsistent_usage(mutation):
    value = report()
    mutation(value)
    with pytest.raises(check.Rejected): check.curate(value, source_sha256="1" * 64)


@pytest.mark.parametrize("field,changed", [
    ("budgets", {**check.CONTRACT.BUDGETS, "stt_seconds": 26}),
    ("grant_seconds", 181), ("input", {"sha256": "f" * 64}),
    ("stt", {"requested_model": "prisma-v2.5", "provider_model": None}),
    ("prompt_version", "old-prompt"), ("model", "different-model"),
    ("limits", {"stt_recognition_deadline_seconds": 30}),
])
def test_even_rehashed_plan_changes_cannot_expand_or_change_the_approved_contract(field, changed):
    value = report()
    value["plan"][field] = changed
    value["plan"]["plan_sha256"] = check.CONTRACT.shared.digest({key: val for key, val in value["plan"].items() if key != "plan_sha256"})
    with pytest.raises(check.Rejected, match="reviewed"): check.curate(value, source_sha256="1" * 64)


def test_typed_plan_mutation_cannot_reuse_numeric_hash():
    value = report()
    value["plan"]["budgets"]["stt_connections"] = True
    with pytest.raises(check.Rejected): check.curate(value, source_sha256="1" * 64)


def test_partial_timeout_retains_unknown_timings_and_safe_fixed_class():
    value = report()
    for field in (*check.TIMINGS, "recognized_text", "translated_text", "target_synthesis"):
        value.pop(field)
    value.update(status="stopped_no_retry", error_stage="stt", error_class="timeout")
    value["used"] = {**{key: 0 for key in check.CONTRACT.BUDGETS}, "stt_seconds": 19, "stt_connections": 1}
    public = check.curate(value, source_sha256="2" * 64)
    assert public["error_class"] == "timeout" and public["error_stage"] == "stt"
    assert all(value is None for value in public["timings"].values())
    assert public["flow_closed"] and public["cost_reference"]["local_usage_reference_inr"] == .1425


def test_cancelled_or_failed_closure_keeps_unknown_usage_and_never_claims_completion():
    value = report()
    value.update(status="cancelled", error_stage="cancelled", error_class="cancelled", used=None,
                 flow_status=None, cleanup_errors=["flow_close_failed"])
    public = check.curate(value, source_sha256="3" * 64)
    assert public["used"] is None and not public["flow_closed"] and not public["cleanup_complete"]
    assert public["cost_reference"]["local_usage_reference_inr"] is None


def test_import_binds_original_bytes_is_idempotent_and_replaces_only_its_own_null_or_type(tmp_path, capsys):
    source, output = tmp_path / "report.json", tmp_path / "public.json"
    raw = json.dumps(report(), ensure_ascii=False).encode()
    source.write_bytes(raw)
    output.write_text("null\n")
    assert check.main(["--input", str(source), "--output", str(output)]) == 0
    public = json.loads(output.read_text(encoding="utf-8"))
    assert public["source_report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert check.import_file(source, output) == public
    original_bytes = output.read_bytes()
    changed = deepcopy(report())
    changed["wall_seconds"] = 13
    source.write_text(json.dumps(changed))
    with pytest.raises(check.Rejected): check.import_file(source, output)
    assert output.read_bytes() == original_bytes
    assert check.import_file(source, output, replace=True)["wall_seconds"] == 13
    assert "provider_calls_made_by_importer" in capsys.readouterr().out


def test_original_two_case_evidence_is_preserved_even_with_replace_flag(tmp_path):
    source, output = tmp_path / "followup.json", tmp_path / "original.json"
    source.write_text(json.dumps(report()))
    output.write_text('{"record_type":"controlled_hindi_tamil_provider_evidence","status":"stopped_no_retry"}')
    original = output.read_bytes()
    with pytest.raises(check.Rejected): check.import_file(source, output, replace=True)
    assert output.read_bytes() == original


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'x' * 1_048_577],
                         ids=["duplicate-keys", "non-finite", "oversized"])
def test_ambiguous_or_oversized_json_is_rejected(raw):
    with pytest.raises(check.Rejected): check.decode(raw)


def test_invalid_import_does_not_echo_source_or_create_output(tmp_path, capsys):
    source, output = tmp_path / "input.json", tmp_path / "output.json"
    source.write_text('{"api_key":"NEVER-ECHO-THIS"}')
    assert check.main(["--input", str(source), "--output", str(output)]) == 2
    captured = capsys.readouterr()
    assert "NEVER-ECHO-THIS" not in captured.out + captured.err and not output.exists()
