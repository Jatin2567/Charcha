"""Check an operator-supplied GPU host snapshot offline; never connects or starts resources."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

REQUIREMENTS = {
    "os": "Linux", "architecture": "x86_64", "gpu": "one A100/H100-class 80 GB GPU",
    "gpu_minimum_total_mib": 76000, "gpu_minimum_free_mib": 72000,
    "driver_minimum_major": 580, "free_disk_minimum_gib": 150,
    "host_ram_minimum_gib": 64, "docker_daemon_access": True,
    "compose_minimum": "2.30.0", "nvidia_container_runtime": True,
    "maximum_session_seconds": 7200,
    "note": "Conservative admission checks for the pinned CUDA 13 candidate, not proof the model fits or meets latency targets.",
}


def numeric_at_least(value: object, minimum: float) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and value >= minimum


def version(value: object) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", value):
        return (0, 0, 0)
    parts = [int(part) for part in value.split(".")]
    return tuple((parts + [0, 0, 0])[:3])


def evaluate(snapshot: dict, *, now: datetime | None = None) -> dict:
    """Consume reported facts; do not claim independently verified host access."""
    if not isinstance(snapshot, dict):
        raise ValueError("Expected a JSON object")
    now = now or datetime.now(timezone.utc)
    checks = []

    def check(name: str, ok: bool, detail: str):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    host = snapshot.get("host", {})
    if not isinstance(host, dict):
        host = {}
    check("linux_amd64", host.get("os") == "Linux" and host.get("architecture") in {"x86_64", "amd64"},
          "The immutable container manifest is Linux AMD64.")
    check("host_ram", numeric_at_least(host.get("ram_gib"), REQUIREMENTS["host_ram_minimum_gib"]),
          "At least 64 GiB host memory for the initial test; runtime allocation remains unverified.")
    check("free_disk", numeric_at_least(host.get("free_disk_gib"), REQUIREMENTS["free_disk_minimum_gib"]),
          "150 GiB free on the actual Docker/model cache filesystem; a planning allowance, not model size.")
    check("docker_access", host.get("docker_daemon_access") is True, "Docker daemon is accessible to the chosen operator.")
    check("compose_version", version(host.get("compose_version")) >= (2, 30, 0), "Compose 2.30+ supports literal credential files.")
    check("nvidia_container_runtime", host.get("nvidia_container_runtime") is True,
          "NVIDIA Container Toolkit must already be configured; this check installs nothing.")
    gpus = host.get("gpus", [])
    if not isinstance(gpus, list):
        gpus = []
    # The generated one-GPU profile uses the first/default visible GPU; another
    # adequate GPU does not make an occupied or undersized first GPU acceptable.
    gpu = gpus[0] if gpus and isinstance(gpus[0], dict) else {}
    check("gpu_memory", numeric_at_least(gpu.get("total_mib"), 76000) and numeric_at_least(gpu.get("free_mib"), 72000),
          "First visible GPU has at least 76,000 MiB total and 72,000 MiB free; multiple small GPUs are not added together.")
    check("driver_branch", version(gpu.get("driver_version"))[0] >= 580,
          "Use R580+ for the CUDA 13 candidate; older forward-compatibility setups need separate validation.")
    session = snapshot.get("session", {})
    if not isinstance(session, dict):
        session = {}
    resource = session.get("resource", "")
    match = re.fullmatch(r"projects/([a-z][a-z0-9-]{4,28}[a-z0-9])/zones/([a-z]+-[a-z]+\d-[a-z])/instances/([a-z](?:[a-z0-9-]{0,61}[a-z0-9])?)", resource) if isinstance(resource, str) else None
    check("exact_resource", match is not None, "Record the exact project, zone and VM; commands never use a wildcard.")
    seconds = session.get("maximum_seconds")
    check("time_budget", numeric_at_least(seconds, 30) and seconds <= 7200, "Approve a 30–7,200-second session including startup and downloads.")
    check("cost_budget", numeric_at_least(session.get("maximum_cost_inr"), 0.01),
          "The owner must approve a monetary ceiling from the actual quote; no price is guessed here.")
    stop = session.get("stop_guard", {})
    if not isinstance(stop, dict):
        stop = {}
    check("stop_guard", stop.get("verified_in_provider") is True and stop.get("action") == "STOP"
          and stop.get("resource") == resource and numeric_at_least(stop.get("maximum_seconds"), 30)
          and numeric_at_least(seconds, 30) and stop.get("maximum_seconds") <= seconds,
          "Provider-side maximum runtime must be verified on this exact VM; an email alert is not a stop guard.")
    captured = snapshot.get("captured_at")
    try:
        at = datetime.fromisoformat(captured.replace("Z", "+00:00")) if isinstance(captured, str) else None
        fresh = at is not None and at.tzinfo is not None and 0 <= (now - at).total_seconds() <= 1800
    except (ValueError, TypeError):
        fresh = False
    check("fresh_snapshot", fresh, "Host/stop facts must be checked within 30 minutes of this review.")
    commands = None
    if match:
        project, zone, name = match.groups()
        commands = {
            "inspect_only": ["gcloud", "compute", "instances", "describe", name, "--project", project, "--zone", zone, "--format=json"],
            "stop_after_test": ["gcloud", "compute", "instances", "stop", name, "--project", project, "--zone", zone],
        }
    return {"schema_version": 1, "kind": "evon_host_preflight", "offline": True, "network_calls": 0,
            "source": "operator_supplied_snapshot_not_independently_verified",
            "status": "ready_for_gpu_acceptance" if all(c["passed"] for c in checks) else "blocked",
            "gpu_runtime_verified": False, "checks": checks, "commands_for_owner_review_only": commands,
            "note": "No commands executed. Approval and current provider/runtime checks remain required. Stop the VM, not only its container; retained disks/IPs may remain billable."}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate(json.loads(args.snapshot.read_text(encoding="utf-8"))) if args.snapshot else {
            "schema_version": 1, "offline": True, "network_calls": 0, "requirements": REQUIREMENTS,
            "status": "awaiting_host_snapshot", "example": "deploy/evon/gcp-session.example.json"}
        encoded = json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as output:
                output.write(encoded + "\n")
        else:
            print(encoded)
        return 1 if result["status"] == "blocked" else 0
    except (ValueError, OSError, TypeError):
        print("Invalid snapshot or output path. See docs/GPU_TESTING.md.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
