"""Operator grants and manual evidence, exclusively local deterministic fixtures."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from charcha.config import Settings
from charcha.errors import ProviderError
from charcha.providers.evon import EvonTranslator
from charcha.providers.gnani import GnaniSpeech
from charcha.services.usage import UsageGuard, provider_flow, provider_room


def settings(**values):
    return Settings(mode="live", usage_require_flow_approval=True, _env_file=None, **values)


def approve(guard, budgets=None, **values):
    return guard.approve_flow(purpose="gnani_speech_check", seconds=30,
                              budgets=budgets or {"tts_requests": 1, "tts_characters": 20}, **values)


def row(guard, key):
    return next(resource for resource in guard.snapshot()["resources"] if resource["key"] == key)


def test_room_and_queued_turns_share_only_the_original_approval():
    guard = UsageGuard(settings(usage_require_room_scope=True))
    first, second = "abcdef012345", "abcdef012346"
    params = dict(purpose="live_interpretation", seconds=30,
                  budgets={key: 20 for key in ("stt_seconds", "stt_connections", "mt_requests",
                                                "mt_characters", "tts_requests", "tts_characters")})
    queued_before = guard.queued_turn_flow(first)
    with pytest.raises(ValueError, match="meeting code"):
        guard.approve_flow(**params)
    flow = guard.approve_flow(room_code=first.upper(), **params)
    assert guard.conference_capacity(1, room_code=second)["status"] == "locked"
    assert guard.conference_capacity(1, room_code=first)["status"] == "approved"
    assert "room_digest" not in guard.public_snapshot()["programme"]["flows"][0]
    with pytest.raises(ProviderError):
        guard.reserve({"mt_requests": 1})
    with provider_room(second), pytest.raises(ProviderError):
        guard.reserve({"stt_seconds": 1})
    with provider_room(first), provider_flow(queued_before), pytest.raises(ProviderError):
        guard.reserve({"tts_requests": 1})
    queued_during = guard.queued_turn_flow(first)
    assert queued_during == flow["id"]
    with provider_room(first), provider_flow(queued_during):
        guard.reserve({"mt_requests": 1})
    used = guard.inspect_flow(flow["id"])["used"]
    assert sum(used.values()) == used["mt_requests"] == 1
    guard.close_flow(flow["id"])
    next_flow = guard.approve_flow(room_code=first, **params)
    with provider_room(first), provider_flow(queued_during), pytest.raises(ProviderError):
        guard.reserve({"tts_requests": 1})
    assert not any(guard.inspect_flow(next_flow["id"])["used"].values())


def test_unscoped_grant_cannot_open_a_strict_meeting_after_restart():
    guard = UsageGuard(settings())
    flow = guard.approve_flow(purpose="live_interpretation", seconds=30, budgets={"mt_requests": 5})
    guard.close()
    strict = UsageGuard(settings(usage_require_room_scope=True))
    with provider_room("abcdef123456"), pytest.raises(ProviderError):
        strict.reserve({"mt_requests": 1})
    with strict.bind_flow(flow["id"]):
        strict.reserve({"mt_requests": 1})
    assert strict.inspect_flow(flow["id"])["used"]["mt_requests"] == 1


def test_approval_is_default_and_no_grant_blocks_without_daily_debit(monkeypatch):
    monkeypatch.delenv("USAGE_REQUIRE_FLOW_APPROVAL")
    assert Settings(_env_file=None).usage_require_flow_approval is True
    guard = UsageGuard(settings())
    with pytest.raises(ProviderError, match="Operator approval") as error:
        guard.reserve({"tts_requests": 1, "tts_characters": 5})
    assert not error.value.retryable
    assert row(guard, "tts_requests")["used"] == 0
    assert guard.snapshot()["approval"]["status"] == "locked"
    assert guard.snapshot()["programme"]["balance"] is None


def test_one_grant_survives_restart_and_unspecified_resources_are_zero():
    first = UsageGuard(settings())
    flow = approve(first)
    assert len(flow["budgets"]) == 7
    assert flow["budgets"]["voice_enrollments"] == 0
    first.close()
    second = UsageGuard(settings())
    assert second.snapshot()["approval"]["active_flow_id"] == flow["id"]
    second.reserve({"tts_requests": 1, "tts_characters": 5})
    with pytest.raises(ProviderError, match="flow resource budget"):
        second.reserve({"tts_requests": 1, "tts_characters": 5})
    with pytest.raises(ProviderError, match="flow resource budget"):
        second.reserve({"voice_enrollments": 1})
    assert row(second, "tts_requests")["used"] == 1
    assert second.inspect_flow(flow["id"])["used"]["tts_characters"] == 5


def test_daily_failure_rolls_back_flow_budget_together():
    guard = UsageGuard(settings(usage_tts_requests_per_day=0))
    flow = approve(guard)
    with pytest.raises(ProviderError, match="Daily credit safeguard"):
        guard.reserve({"tts_requests": 1, "tts_characters": 5})
    assert row(guard, "tts_characters")["used"] == 0
    assert guard.inspect_flow(flow["id"])["used"]["tts_requests"] == 0


def test_expiry_and_close_relock_without_overspending():
    current = [datetime(2026, 10, 24, tzinfo=UTC)]
    guard = UsageGuard(settings(), now=lambda: current[0])
    flow = approve(guard)
    with pytest.raises(ValueError, match="existing flow"):
        approve(guard)
    current[0] += timedelta(seconds=30)
    assert guard.inspect_flow(flow["id"])["status"] == "expired"
    with pytest.raises(ProviderError, match="Operator approval"):
        guard.reserve({"tts_requests": 1})
    assert row(guard, "tts_requests")["used"] == 0
    fresh = approve(guard)
    guard.close_flow(fresh["id"])
    assert guard.inspect_flow(fresh["id"])["status"] == "closed"
    with pytest.raises(ProviderError, match="Operator approval"):
        guard.reserve({"tts_requests": 1})


def test_concurrent_grants_and_reservations_are_atomic_across_guards():
    guards = [UsageGuard(settings()), UsageGuard(settings())]
    for guard in guards:
        guard.snapshot()  # Initialize schema before independent contending callers.

    def grant(index):
        try:
            return approve(guards[index % 2], {"tts_requests": 7, "tts_characters": 70})
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(flow is not None for flow in executor.map(grant, range(20))) == 1

    def reserve(index):
        try:
            guards[index % 2].reserve({"tts_requests": 1, "tts_characters": 10})
            return True
        except ProviderError:
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(reserve, range(30))) == 7
    snapshot = guards[0].snapshot()
    assert row(guards[0], "tts_requests")["used"] == 7
    assert snapshot["programme"]["flows"][0]["used"]["tts_characters"] == 70
    assert snapshot["approval"]["status"] == "locked"


async def test_expired_stream_cannot_spend_replacement_grant():
    current = [datetime(2026, 10, 24, tzinfo=UTC)]
    guard = UsageGuard(settings(), now=lambda: current[0])
    flow = approve(guard, {"stt_connections": 1, "stt_seconds": 2})
    ready, proceed = asyncio.Event(), asyncio.Event()

    async def inherited_ticker():
        ready.set()
        await proceed.wait()
        with pytest.raises(ProviderError, match="Operator approval"):
            guard.reserve({"stt_seconds": 1})

    async with guard.operation({"stt_connections": 1, "stt_seconds": 1}, stt=True):
        task = asyncio.create_task(inherited_ticker())
        await ready.wait()
        current[0] += timedelta(seconds=31)
        fresh = approve(guard, {"stt_seconds": 3})
        proceed.set()
        await task
    assert guard.inspect_flow(flow["id"])["used"]["stt_seconds"] == 1
    assert guard.inspect_flow(fresh["id"])["used"]["stt_seconds"] == 0
    assert row(guard, "stt_seconds")["used"] == 1


def test_explicit_binding_prevents_another_grant_from_replacing_requested_id():
    guard = UsageGuard(settings())
    old = approve(guard)
    with guard.bind_flow(old["id"]):
        guard.close_flow(old["id"])
        fresh = approve(guard)
        with pytest.raises(ProviderError, match="Operator approval"):
            guard.reserve({"tts_requests": 1})
    assert guard.inspect_flow(fresh["id"])["used"]["tts_requests"] == 0


async def test_unapproved_adapters_never_contact_any_provider(monkeypatch):
    guard = UsageGuard(settings(evon_base_url="https://fixture.invalid/v1", evon_model="fixture"))
    speech = GnaniSpeech(guard.settings, guard)
    translator = EvonTranslator(guard.settings, guard)
    await translator.client.aclose()
    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("Unapproved provider call")

    translator.client = httpx.AsyncClient(transport=httpx.MockTransport(forbidden))
    monkeypatch.setattr("charcha.providers.gnani.websockets.connect", forbidden)
    await speech.client.aclose()
    speech.client = httpx.AsyncClient(transport=httpx.MockTransport(forbidden))

    async def audio():
        yield b"\x00" * 1024

    try:
        with pytest.raises(ProviderError, match="Operator approval"):
            await translator.translate("text", "hi", "ta")
        with pytest.raises(ProviderError, match="Operator approval"):
            await speech.enroll(b"reference")
        with pytest.raises(ProviderError, match="Operator approval"):
            _ = [chunk async for chunk in speech.synthesize("text", "hi")]
        with pytest.raises(ProviderError, match="Operator approval"):
            _ = [part async for part in speech.transcribe(audio(), "hi")]
        assert calls == []
        assert all(resource["used"] == 0 for resource in guard.snapshot()["resources"])
    finally:
        await speech.aclose()
        await translator.aclose()


async def test_stt_ticker_closes_socket_when_flow_seconds_exhausted(monkeypatch):
    class Socket:
        closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            self.closed = True

        async def recv(self):
            return '{"type":"connected"}'

        async def send(self, _):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Event().wait()

    guard = UsageGuard(settings())
    flow = approve(guard, {"stt_connections": 1, "stt_seconds": 1})
    speech, socket = GnaniSpeech(guard.settings, guard), Socket()
    monkeypatch.setattr("charcha.providers.gnani.websockets.connect", lambda *_a, **_kw: socket)

    async def audio():
        yield b"\x00" * 1024
        await asyncio.Event().wait()

    try:
        with pytest.raises(ProviderError, match="flow resource budget"):
            async with asyncio.timeout(2):
                _ = [part async for part in speech.transcribe(audio(), "hi")]
        assert socket.closed
        assert guard.inspect_flow(flow["id"])["used"]["stt_seconds"] == 1
    finally:
        await speech.aclose()


def test_demo_snapshot_has_no_database_or_manual_balance_claim(tmp_path):
    path = tmp_path / "not-created.sqlite3"
    guard = UsageGuard(Settings(mode="demo", usage_db_path=path, usage_require_flow_approval=True,
                               usage_reported_request_rate_inr=0.06, _env_file=None))
    for _ in range(3):
        snapshot = guard.snapshot()
        assert snapshot["approval"]["status"] == "demo"
        assert snapshot["programme"]["source"] == "not_connected"
        assert snapshot["programme"]["balance"] is None
        assert snapshot["programme"]["flows"] == []
        assert snapshot["programme"]["quoted_rate"]["scope"] == "unconfirmed"
    assert not path.exists()
    with pytest.raises(ProviderError, match="demo"):
        approve(guard)
    assert not path.exists()


def test_manual_rupee_balance_and_flow_delta_are_labelled_not_estimated():
    current = [datetime(2026, 10, 24, 10, tzinfo=UTC)]
    guard = UsageGuard(settings(usage_reported_request_rate_inr=0.06), now=lambda: current[0])
    guard.record_programme_balance(balance=3500, unit="INR", observed_at=current[0], source="user_reported")
    programme = guard.snapshot()["programme"]
    assert (programme["unit"], programme["balance"], programme["source"]) == ("INR", 3500, "user_reported")
    assert programme["automatic_sync"] is False
    assert programme["quoted_rate"] == {"amount": 0.06, "currency": "INR", "unit": "request",
                                        "source": "user_reported", "scope": "unconfirmed"}
    flow = approve(guard, before_balance=3500, balance_unit="INR", before_observed_at=current[0])
    guard.reserve({"tts_requests": 1, "tts_characters": 4})
    assert guard.inspect_flow(flow["id"])["balance_delta"] is None
    current[0] += timedelta(seconds=2)
    guard.close_flow(flow["id"])
    current[0] += timedelta(seconds=2)
    reconciled = guard.reconcile_flow(flow_id=flow["id"], after_balance=3499.94,
                                     balance_unit="INR", after_observed_at=current[0])
    assert reconciled["balance_delta"] == 0.06
    assert reconciled["credits_used"] is None
    assert reconciled["credits_source"] == "manual_dashboard_delta"
    assert guard.snapshot()["programme"]["source"] == "manual_dashboard"


def test_programme_credit_delta_is_not_derived_from_reservations():
    current = [datetime(2026, 10, 24, tzinfo=UTC)]
    guard = UsageGuard(settings(), now=lambda: current[0])
    flow = approve(guard, before_balance=20, balance_unit="programme_credits", before_observed_at=current[0])
    guard.reserve({"tts_requests": 1})
    guard.close_flow(flow["id"])
    result = guard.reconcile_flow(flow_id=flow["id"], after_balance=18.5,
                                 balance_unit="programme_credits", after_observed_at=current[0])
    assert result["credits_used"] == 1.5
    assert result["used"]["tts_requests"] == 1


@pytest.mark.parametrize("amount", [-1, float("nan"), float("inf"), True])
def test_invalid_balances_do_not_mutate_evidence(amount):
    guard = UsageGuard(settings())
    with pytest.raises(ValueError, match="finite nonnegative"):
        guard.record_programme_balance(balance=amount, unit="INR", observed_at=guard.now())
    assert guard.snapshot()["programme"]["balance"] is None


def test_invalid_balance_timestamps_units_and_topups_roll_back_all_changes():
    current = [datetime(2026, 10, 24, 12, tzinfo=UTC)]
    guard = UsageGuard(settings(), now=lambda: current[0])
    with pytest.raises(ValueError, match="future"):
        guard.record_programme_balance(balance=3500, unit="INR", observed_at=current[0] + timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        guard.record_programme_balance(balance=3500, unit="INR", observed_at="2026-10-24T10:00:00")
    with pytest.raises(ValueError, match="together"):
        approve(guard, before_balance=3500)
    flow = approve(guard, before_balance=10, balance_unit="INR", before_observed_at=current[0])
    with pytest.raises(ValueError, match="Close the flow"):
        guard.reconcile_flow(flow_id=flow["id"], after_balance=9, balance_unit="INR", after_observed_at=current[0])
    current[0] += timedelta(seconds=3)
    guard.close_flow(flow["id"])
    for amount, unit, observed in ((11, "INR", current[0]), (9, "programme_credits", current[0]),
                                   (9, "INR", current[0] - timedelta(seconds=1))):
        with pytest.raises(ValueError):
            guard.reconcile_flow(flow_id=flow["id"], after_balance=amount, balance_unit=unit, after_observed_at=observed)
    assert guard.inspect_flow(flow["id"])["balance_delta"] is None
    assert guard.snapshot()["programme"]["balance"] == 10


@pytest.mark.parametrize("values", [
    {"seconds": 301}, {"seconds": 0}, {"purpose": "private transcript"},
    {"budgets": {"tts_requests": -1}}, {"budgets": {"voice": 1}}, {"budgets": {}},
    {"budgets": {"tts_requests": True}},
])
def test_invalid_flow_grants_are_rejected(values):
    guard = UsageGuard(settings())
    request = {"purpose": "gnani_speech_check", "seconds": 30, "budgets": {"tts_requests": 1}}
    request.update(values)
    with pytest.raises(ValueError):
        guard.approve_flow(**request)
    assert guard.snapshot()["programme"]["flows"] == []


def test_flow_history_is_bounded_redacted_and_metrics_allowlisted():
    current = [datetime(2026, 10, 24, tzinfo=UTC)]
    guard = UsageGuard(settings(), now=lambda: current[0])
    for index in range(56):
        flow = approve(guard)
        guard.close_flow(flow["id"])
        current[0] += timedelta(seconds=1)
    snapshot = guard.snapshot()
    assert len(snapshot["programme"]["flows"]) == 50
    assert len(set(item["id"] for item in snapshot["programme"]["flows"])) == 50
    guard.record_flow_metrics(flow["id"], {"tts_first_pcm_ms": 312.5, "error_stage": "none"})
    assert guard.inspect_flow(flow["id"])["metrics"] == {"tts_first_pcm_ms": 312.5, "error_stage": "none"}
    for metrics in ({"text": "private"}, {"tts_total_ms": float("nan")}, {"error_stage": "private error"}):
        with pytest.raises(ValueError):
            guard.record_flow_metrics(flow["id"], metrics)
    body = json.dumps(guard.snapshot())
    assert "private" not in body
    assert "api_key" not in body
    with sqlite3.connect(guard.settings.usage_db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM operator_flows").fetchone()[0] == 50


def test_storage_failure_never_reports_an_active_grant(tmp_path):
    bad = tmp_path / "bad.sqlite3"
    bad.write_bytes(b"corrupt")
    guard = UsageGuard(settings(usage_db_path=bad))
    with pytest.raises(ProviderError, match="storage"):
        approve(guard)
    snapshot = guard.snapshot()
    assert snapshot["approval"]["status"] == "unavailable"
    assert snapshot["programme"]["balance"] is None


def test_cli_plan_does_not_read_env_create_ledger_or_call_api(monkeypatch, tmp_path, capsys):
    script = Path(__file__).resolve().parents[2] / "scripts" / "provider_flow.py"
    spec = importlib.util.spec_from_file_location("provider_flow_local", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("USAGE_DB_PATH", str(tmp_path / "must-not-exist.sqlite3"))
    monkeypatch.setattr(module, "Settings", lambda **_: (_ for _ in ()).throw(AssertionError("Plan read settings")))
    assert module.main(["plan", "--purpose", "gnani_speech_check", "--seconds", "60", "--tts-requests", "1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["budgets"]["tts_requests"] == 1
    assert result["provider_credit_cost"] is None
    assert not (tmp_path / "must-not-exist.sqlite3").exists()


def test_rate_card_is_reference_only_and_never_debits_or_estimates_balances():
    guard = UsageGuard(settings(usage_stt_inr_per_hour=27, usage_tts_inr_per_10000_characters=27))
    approve(guard)
    guard.reserve({"tts_requests": 1, "tts_characters": 4})
    programme = guard.snapshot()["programme"]
    assert programme["balance"] is None
    assert programme["flows"][0]["balance_delta"] is None
    assert programme["quoted_rate"] is None
    assert programme["pricing"] == {
        "currency": "INR", "source": "user_provided_pricing_table",
        "reference_url": "https://app.gnani.ai/voice/pricing", "stt_per_hour": 27,
        "tts_per_10000_characters": 27, "voice_enrollment": None, "rounding": "unconfirmed",
    }


@pytest.mark.parametrize("field", ["usage_stt_inr_per_hour", "usage_tts_inr_per_10000_characters"])
@pytest.mark.parametrize("amount", [-1, float("nan"), float("inf")])
def test_rate_card_rejects_invalid_values(field, amount):
    with pytest.raises(ValidationError):
        settings(**{field: amount})


def test_public_usage_hides_private_balances_but_preserves_reference_controls():
    current = datetime(2026, 10, 24, tzinfo=UTC)
    guard = UsageGuard(settings(usage_stt_inr_per_hour=27), now=lambda: current)
    assert guard.settings.usage_show_private_balance is False
    flow = approve(guard, before_balance=4321.12, balance_unit="INR", before_observed_at=current)
    guard.close_flow(flow["id"])
    guard.reconcile_flow(flow_id=flow["id"], after_balance=4320.76,
                         balance_unit="INR", after_observed_at=current)
    guard.record_flow_metrics(flow["id"], {"tts_first_pcm_ms": 180})
    public = guard.public_snapshot()
    programme = public["programme"]
    assert (programme["source"], programme["unit"], programme["balance"], programme["observed_at"]) == (
        "not_connected", None, None, None,
    )
    evidence = programme["flows"][0]
    for key in ("before_balance", "before_observed_at", "after_balance", "after_observed_at",
                "balance_unit", "balance_delta", "credits_used"):
        assert evidence[key] is None
    assert evidence["credits_source"] == "unknown"
    assert evidence["metrics"]["tts_first_pcm_ms"] == 180
    assert evidence["budgets"]["tts_requests"] == 1
    assert programme["pricing"]["stt_per_hour"] == 27
    assert "4321.12" not in json.dumps(public)
    assert "4320.76" not in json.dumps(public)
    assert "operator CLI" in programme["detail"]
    # Redaction never mutates the persisted evidence or the operator view.
    assert guard.snapshot()["programme"]["balance"] == 4320.76
    assert guard.inspect_flow(flow["id"])["balance_delta"] == 0.36


def test_public_usage_hides_programme_credit_delta_and_user_reported_snapshot():
    current = datetime(2026, 10, 24, tzinfo=UTC)
    guard = UsageGuard(settings(), now=lambda: current)
    flow = approve(guard, before_balance=80, balance_unit="programme_credits", before_observed_at=current)
    guard.close_flow(flow["id"])
    guard.reconcile_flow(flow_id=flow["id"], after_balance=78.5,
                         balance_unit="programme_credits", after_observed_at=current)
    public = guard.public_snapshot()["programme"]
    assert public["flows"][0]["credits_used"] is None
    assert public["flows"][0]["balance_delta"] is None
    guard.record_programme_balance(balance=3500, unit="INR", observed_at=current, source="user_reported")
    assert guard.public_snapshot()["programme"]["balance"] is None
    assert guard.snapshot()["programme"]["source"] == "user_reported"


def test_explicit_local_operator_view_retains_manual_financial_evidence():
    current = datetime(2026, 10, 24, tzinfo=UTC)
    guard = UsageGuard(settings(usage_show_private_balance=True), now=lambda: current)
    flow = approve(guard, before_balance=20, balance_unit="programme_credits", before_observed_at=current)
    guard.close_flow(flow["id"])
    guard.reconcile_flow(flow_id=flow["id"], after_balance=19,
                         balance_unit="programme_credits", after_observed_at=current)
    public = guard.public_snapshot()["programme"]
    assert public["balance"] == 19
    assert public["unit"] == "programme_credits"
    assert public["flows"][0]["credits_used"] == 1
