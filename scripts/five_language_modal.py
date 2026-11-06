"""Scoped lifetime of the existing private Modal model for the five-language stage."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import json
import os
import re
import subprocess
import time

from check_modal_readiness import ROOT, check_readiness, load_credentials

CLI = ROOT / "work/modal-cli-py312/.venv/Scripts/modal.exe"
APP = "artha-evon-test"
PROFILE = "artha-mesh"
ALLOCATION_FILE = ROOT / "deploy/modal/allocation.json"
GPU_RATE_KEYS = {"A100-80GB": "gpu_hour_cost_a100_80gb", "H100": "gpu_hour_cost_h100"}
REGIONS = {"ap", "us", "eu", "ap-northeast", "ap-southeast", "ap-south",
           "us-east", "us-west", "us-central", "us-south", "eu-west", "eu-north", "eu-south"}
REGION_MULTIPLIER = Decimal("1.75")  # Conservative even for broad regions (currently 1.15).


def amount(value, name, *, allow_zero=False):
    try:
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise ValueError
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or (result == 0 and not allow_zero):
            raise ValueError
        return result
    except (ValueError, InvalidOperation):
        raise ValueError(f"Invalid or missing {name}") from None


def choices(value):
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not value or any(not isinstance(x, str) for x in value):
        raise ValueError("Allocation needs a nonempty GPU/region selection")
    return value


def load_allocation():
    allocation = json.loads(ALLOCATION_FILE.read_text(encoding="utf8"))
    validate_allocation(allocation)
    return allocation


def validate_allocation(allocation):
    if not isinstance(allocation, dict) or set(allocation) != {
            "gpu", "region", "cpu_cores", "memory_gib", "max_containers"}:
        raise ValueError("Review the complete Modal allocation")
    if not set(choices(allocation["gpu"])) <= GPU_RATE_KEYS.keys():
        raise ValueError("Unpriced GPU selection; update the reviewed cost mapping first")
    if not set(choices(allocation["region"])) <= REGIONS:
        raise ValueError("Unreviewed Modal region")
    for key in ("cpu_cores", "memory_gib", "max_containers"):
        if type(allocation[key]) is not int or allocation[key] <= 0:
            raise ValueError("Allocation resources must be positive integers")


def cli(arguments, env=None, timeout=45):
    result = subprocess.run([str(CLI), *arguments, "--profile", PROFILE], cwd=ROOT, env=env,
                            capture_output=True, encoding="utf8", errors="replace", timeout=timeout)
    if result.returncode:
        raise RuntimeError("Modal command failed: " + " ".join(arguments[:2]))
    return result.stdout


def billing():
    snapshot = json.loads(cli(["billing", "summary", "--json"]))
    return {key: snapshot[key] for key in ("metered_cost", "billed_cost")}


def reserve_breakdown(rates, seconds, *, overhead_usd=None, allocation=None, owner_hour=False):
    """Offline estimate, not a provider-enforced cap or an authorization to spend."""
    maximum = 3600 if owner_hour else 1800
    if type(seconds) is not int or not 0 < seconds <= maximum:
        raise ValueError(f"Maximum stage lifetime is {maximum // 60} minutes")
    overhead = amount(overhead_usd, "reviewed build/CPU/storage/network allowance", allow_zero=True)
    allocation = load_allocation() if allocation is None else allocation
    validate_allocation(allocation)
    if not isinstance(rates, dict):
        raise ValueError("Missing current rates")
    gpu_rates = {gpu: amount(rates.get(GPU_RATE_KEYS[gpu]), f"rate for {gpu}")
                 for gpu in choices(allocation["gpu"])}
    cpu = amount(rates.get("cpu_hour_cost"), "CPU rate")
    mem = amount(rates.get("mem_gib_hour_cost"), "memory rate")
    # Read the same GPU/CPU/RAM/container configuration as the deployment. Price
    # the most expensive allowed fallback, including startup within the window
    # and two extra minutes for teardown. Other costs need a reviewed allowance.
    hourly = (max(gpu_rates.values()) + allocation["cpu_cores"] * cpu
              + allocation["memory_gib"] * mem) * REGION_MULTIPLIER * allocation["max_containers"]
    serving = hourly * Decimal(seconds + 120) / 3600
    total = (serving + overhead).quantize(Decimal(".01"), rounding=ROUND_CEILING)
    return {"allocation": allocation, "gpu_hourly_rates_usd": {k: str(v) for k, v in gpu_rates.items()},
            "cpu_hourly_rate_usd": str(cpu), "memory_gib_hourly_rate_usd": str(mem),
            "region_multiplier": str(REGION_MULTIPLIER), "duration_s": seconds,
            "teardown_allowance_s": 120, "serving_hourly_usd": str(hourly),
            "serving_reserve_usd": str(serving), "other_cost_allowance_usd": str(overhead),
            "reserved_usd": str(total), "estimate_only": True}


def reserve_usd(rates, seconds, *, overhead_usd=None, allocation=None):
    return Decimal(reserve_breakdown(rates, seconds, overhead_usd=overhead_usd,
                                    allocation=allocation)["reserved_usd"])


@contextmanager
def bounded_session(folder, host, deadline, *, overhead_usd=None, workspace_ceiling_usd=None, owner_hour=False):
    if host != "https://jatin2567--artha-evon-test-serve.ap-south.modal.run":
        raise ValueError("Unexpected private model endpoint")
    start = time.time()
    seconds = int(deadline - start)
    # Reject unreviewed allowances before any account query or cloud mutation.
    amount(overhead_usd, "reviewed build/CPU/storage/network allowance", allow_zero=True)
    ceiling = amount(workspace_ceiling_usd, "reviewed workspace gross usage ceiling")
    if ceiling > (10 if owner_hour else 5):
        raise ValueError("This runner cannot exceed the reviewed workspace ceiling")
    cost = reserve_breakdown(json.loads(cli(["billing", "rates", "--json"])), seconds,
                             overhead_usd=overhead_usd, owner_hour=owner_hour)
    reserve = Decimal(cost["reserved_usd"])
    if owner_hour and (reserve > Decimal("6.54") or cost["allocation"] != {
        "gpu":"A100-80GB", "region":"ap", "cpu_cores":4, "memory_gib":64,"max_containers":1
    }):
        raise ValueError("Resource selection or reserve exceeds the approved one-hour test")
    before = billing()
    if (amount(before["billed_cost"], "billed cost", allow_zero=True) != 0
            or amount(before["metered_cost"], "metered cost", allow_zero=True) + reserve > ceiling):
        raise RuntimeError("Insufficient verified margin under reviewed workspace ceiling")
    if json.loads(cli(["container", "list", "--json"])):
        raise RuntimeError("Existing workspace compute needs review before deployment")
    # Reject other active versions even when they have scaled to zero.
    for app in json.loads(cli(["app", "list", "--json"])):
        if (app.get("Description") == APP or app.get("description") == APP) and str(
                app.get("State") or app.get("state")).lower() != "stopped":
            raise RuntimeError("Another deployment of this app is active")
    expiry = datetime.fromtimestamp(deadline, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    env = {**os.environ, "MODAL_EVON_SESSION_EXPIRES_AT": expiry, "PYTHONIOENCODING":"utf-8"}
    receipt = {"before": before, "maximum_duration_s": seconds, "reserved_usd": str(reserve),
               "cost_reserve": cost, "workspace_usage_ceiling_usd": str(ceiling),
               "absolute_expiry": expiry, "stopped": False}
    def record():
        (folder / "compute.json").write_text(json.dumps(receipt, indent=2), encoding="utf8")
    record()
    identity = APP
    try:
        output = cli(["deploy", "scripts/modal_evon.py"], env, 240)
        if host not in re.findall(r"https://[A-Za-z0-9_.-]+\.modal\.run", output):
            raise RuntimeError("Unexpected deployment URL")
        info = json.loads(cli(["app", "info", APP, "--json"]))
        if info["description"] != APP or not re.fullmatch("ap-[A-Za-z0-9]+", info["app_id"]):
            raise RuntimeError("Cannot identify owned deployment")
        identity = info["app_id"]
        receipt.update(app_id=identity)
        record()
        print("Private model deployed. Waiting for readiness.", flush=True)
        credentials = load_credentials(ROOT / "work/modal-private/client.json")
        health = asyncio.run(check_readiness(host, credentials, wall_seconds=min(960 if owner_hour else 700, deadline-time.time()-180)))
        (folder / "readiness.json").write_text(json.dumps(health, indent=2))
        if not health["ready"]:
            raise RuntimeError("Private model did not become ready")
        print("Private Evon model ready.", flush=True)
        yield deadline - 30
    finally:
        cli(["app", "stop", identity, "--yes"])
        for _ in range(12):
            info = json.loads(cli(["app", "info", identity, "--json"]))
            if info["lifecycle"]["state"] == "stopped":
                receipt["stopped"] = True
                break
            time.sleep(2)
        record()
        receipt["after"] = billing()
        record()
        if not receipt["stopped"]:
            raise RuntimeError("Verify shutdown of the owned app")
