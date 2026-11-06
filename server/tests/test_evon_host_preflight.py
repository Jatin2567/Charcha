import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import socket

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("evon_host_preflight", ROOT / "scripts" / "evon_host_preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def snapshot():
    resource = "projects/charcha-test-123/zones/asia-southeast1-c/instances/evon-trial"
    return {
        "captured_at": "2026-10-28T11:55:00Z",
        "host": {"os": "Linux", "architecture": "x86_64", "ram_gib": 170, "free_disk_gib": 180,
                 "docker_daemon_access": True, "compose_version": "2.30.3", "nvidia_container_runtime": True,
                 "gpus": [{"total_mib": 81920, "free_mib": 80000, "driver_version": "580.95.05"}]},
        "session": {"resource": resource, "maximum_seconds": 7200, "maximum_cost_inr": 1000,
                    "stop_guard": {"verified_in_provider": True, "action": "STOP", "resource": resource,
                                   "maximum_seconds": 7200}},
    }


def test_ready_means_reported_prerequisites_not_actual_runtime_verified():
    result = preflight.evaluate(snapshot(), now=NOW)
    assert result["status"] == "ready_for_gpu_acceptance"
    assert result["gpu_runtime_verified"] is False
    assert result["network_calls"] == 0
    assert result["source"] == "operator_supplied_snapshot_not_independently_verified"
    assert result["commands_for_owner_review_only"]["stop_after_test"] == [
        "gcloud", "compute", "instances", "stop", "evon-trial", "--project", "charcha-test-123",
        "--zone", "asia-southeast1-c"]


@pytest.mark.parametrize("host_change", [
    {"os": "Windows"}, {"architecture": "aarch64"}, {"ram_gib": 32}, {"free_disk_gib": 149},
    {"free_disk_gib": float("nan")}, {"docker_daemon_access": False}, {"compose_version": "2.29.9"},
    {"compose_version": "not a version"}, {"nvidia_container_runtime": False},
    {"gpus": []}, {"gpus": [{"total_mib": 40960, "free_mib": 40000, "driver_version": "580.95.05"}] * 2},
    {"gpus": [{"total_mib": 81920, "free_mib": 40000, "driver_version": "580.95.05"}]},
    {"gpus": [{"total_mib": 81920, "free_mib": 80000, "driver_version": "570.86.15"}]},
])
def test_missing_or_insufficient_host_facts_block(host_change):
    data = snapshot()
    data["host"].update(host_change)
    assert preflight.evaluate(data, now=NOW)["status"] == "blocked"


@pytest.mark.parametrize("session_change", [
    {"maximum_seconds": 7201}, {"maximum_seconds": True}, {"maximum_cost_inr": None},
    {"resource": "projects/p; echo danger/zones/asia-south1-a/instances/anything"},
])
def test_budget_and_exact_identity_required(session_change):
    data = snapshot()
    data["session"].update(session_change)
    result = preflight.evaluate(data, now=NOW)
    assert result["status"] == "blocked"
    if "resource" in session_change:
        assert result["commands_for_owner_review_only"] is None


@pytest.mark.parametrize("stop_change", [
    {"verified_in_provider": False}, {"action": "DELETE"}, {"maximum_seconds": 7201},
    {"resource": "projects/other-project/zones/asia-south1-a/instances/other"},
])
def test_unverified_or_mismatched_stop_guard_blocks(stop_change):
    data = snapshot()
    data["session"]["stop_guard"].update(stop_change)
    result = preflight.evaluate(data, now=NOW)
    assert result["status"] == "blocked"
    assert next(row for row in result["checks"] if row["check"] == "stop_guard")["passed"] is False


@pytest.mark.parametrize("captured", [None, "invalid", "2026-10-28T11:00:00Z", "2026-10-28T12:01:00Z", "2026-10-28T11:55:00"])
def test_missing_stale_future_or_naive_snapshot_blocks(captured):
    data = snapshot()
    data["captured_at"] = captured
    assert preflight.evaluate(data, now=NOW)["status"] == "blocked"


def test_offline_cli_never_connects_or_executes_commands(monkeypatch, capsys):
    import subprocess

    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline checker attempted execution")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert preflight.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "awaiting_host_snapshot"
    assert report["network_calls"] == 0


def test_example_cannot_misrepresent_a_real_host_as_ready():
    example = json.loads((ROOT / "deploy" / "evon" / "gcp-session.example.json").read_text())
    assert preflight.evaluate(example, now=NOW)["status"] == "blocked"


def test_check_does_not_mutate_or_export_unrelated_snapshot_secrets():
    data = snapshot()
    data["private_key"] = "DO-NOT-EXPORT"
    before = copy.deepcopy(data)
    report = preflight.evaluate(data, now=NOW)
    assert data == before
    assert "DO-NOT-EXPORT" not in json.dumps(report)
