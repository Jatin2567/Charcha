"""Offline financial guard checks: no Modal imports, network or credentials."""
from decimal import Decimal
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import five_language_modal as costs
import run_five_language_calls as batch

RATES = {"gpu_hour_cost_a100_80gb": "2.50", "gpu_hour_cost_h100": "3.95",
         "cpu_hour_cost": ".0473", "mem_gib_hour_cost": ".008"}


def profile(gpu="A100-80GB", region="ap", **overrides):
    return dict(gpu=gpu, region=region, cpu_cores=4, memory_gib=64,
                max_containers=1) | overrides


def test_h100_fallback_uses_highest_rate_with_all_resources_and_rounds_up():
    result = costs.reserve_breakdown(RATES, 1500, overhead_usd=".73",
        allocation=profile(["A100-80GB", "H100"], ["ap", "us", "eu"]))
    assert result["serving_hourly_usd"] == "8.139600"
    assert Decimal(result["serving_reserve_usd"]) == Decimal("3.66282")
    assert result["reserved_usd"] == "4.40"
    assert result["teardown_allowance_s"] == 120
    assert result["estimate_only"] is True


def test_fallback_order_and_region_breadth_cannot_reduce_reserve():
    for gpu in (["A100-80GB", "H100"], ["H100", "A100-80GB"], "H100"):
        for region in ("ap", "us-east", ["ap", "us", "eu"]):
            assert costs.reserve_usd(RATES, 1500, overhead_usd=".73",
                allocation=profile(gpu, region)) == Decimal("4.40")


def test_only_allowed_gpu_needs_a_rate_and_current_configuration_stays_original():
    allocation = costs.load_allocation()
    assert allocation == profile()
    rates = {k: v for k, v in RATES.items() if k != "gpu_hour_cost_h100"}
    assert costs.reserve_usd(rates, 1500, overhead_usd=".73") == Decimal("3.26")
    with pytest.raises(ValueError, match="rate for H100"):
        costs.reserve_usd(rates, 1500, overhead_usd=".73",
                          allocation=profile(["A100-80GB", "H100"]))


@pytest.mark.parametrize("value", [None, "NaN", "Infinity", "-1", True, {}, ""])
@pytest.mark.parametrize("key", list(RATES))
def test_invalid_required_rates_rejected(value, key):
    rates = dict(RATES, **{key: value})
    with pytest.raises(ValueError):
        costs.reserve_usd(rates, 1500, overhead_usd=".73",
                          allocation=profile(["A100-80GB", "H100"]))


@pytest.mark.parametrize("seconds", [0, -1, 1801, float("nan"), 1.5, True, None])
def test_invalid_or_unbounded_duration_rejected(seconds):
    with pytest.raises(ValueError):
        costs.reserve_usd(RATES, seconds, overhead_usd=".73")


@pytest.mark.parametrize("gpu,region", [("B200", "ap"), ([], "ap"),
    (["H100", "unpriced"], "ap"), ("A100-80GB:2", "ap"),
    ("A100-80GB", "unknown-region"), ("A100-80GB", [])])
def test_changed_unpriced_resources_fail_closed(gpu, region):
    with pytest.raises(ValueError):
        costs.reserve_usd(RATES, 1500, overhead_usd=".73", allocation=profile(gpu, region))


def test_more_cpu_memory_and_containers_are_all_counted():
    base = costs.reserve_usd(RATES, 1500, overhead_usd="0", allocation=profile())
    more = costs.reserve_usd(RATES, 1500, overhead_usd="0",
        allocation=profile(cpu_cores=8, memory_gib=128, max_containers=2))
    assert more > 2 * base


@pytest.mark.parametrize("value", [None, "NaN", "Infinity", "-.01", True])
def test_unreviewed_overhead_fails_before_account_access(monkeypatch, tmp_path, value):
    def forbidden(*args, **kwargs):
        pytest.fail("A missing/invalid allowance must fail before any cloud command")
    monkeypatch.setattr(costs, "cli", forbidden)
    with pytest.raises(ValueError):
        with costs.bounded_session(tmp_path,
            "https://jatin2567--artha-evon-test-serve.ap-south.modal.run",
            1500, overhead_usd=value, workspace_ceiling_usd="2.80"):
            pytest.fail("Must not enter paid session")


def test_over_budget_fails_before_deploy_or_health(monkeypatch, tmp_path):
    calls = []
    def fake_cli(args, *unused, **kw):
        calls.append(args)
        assert args == ["billing", "rates", "--json"]
        import json
        return json.dumps(RATES)
    monkeypatch.setattr(costs, "cli", fake_cli)
    monkeypatch.setattr(costs.time, "time", lambda: 0)
    monkeypatch.setattr(costs, "billing", lambda: {"metered_cost": ".73", "billed_cost": "0"})
    with pytest.raises(RuntimeError, match="Insufficient verified margin"):
        with costs.bounded_session(tmp_path,
            "https://jatin2567--artha-evon-test-serve.ap-south.modal.run",
            1500, overhead_usd=".73", workspace_ceiling_usd="2.80"):
            pytest.fail("Over-budget session must never start")
    assert len(calls) == 1


def test_resource_and_allowance_changes_invalidate_reviewed_plan(monkeypatch):
    original = batch.plan(modal_overhead_usd=".73", modal_workspace_ceiling_usd="5")
    changed = batch.plan(modal_overhead_usd=".74", modal_workspace_ceiling_usd="5")
    assert batch.shared.digest(original) != batch.shared.digest(changed)
    allocation = copy.deepcopy(costs.load_allocation())
    allocation["gpu"] = ["A100-80GB", "H100"]
    monkeypatch.setattr(costs, "load_allocation", lambda: allocation)
    changed = batch.plan(modal_overhead_usd=".73", modal_workspace_ceiling_usd="5")
    assert batch.shared.digest(original) != batch.shared.digest(changed)
