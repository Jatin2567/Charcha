"""Offline-first health check for one approved Modal GPU warm-up request.

Modal may return 303 to the same /health URL with a private result query after
150 seconds. Only that continuation is followed; failed requests are not retried.
No settings, environment or credentials are read while making the default plan.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MAX_WALL_SECONDS = 960
MAX_REDIRECTS = 6
DEFAULT_BASE = "https://replace-with-approved-host.modal.run"
CREDENTIAL_KEYS = {"api_key", "modal_key", "modal_secret"}


class Rejected(ValueError):
    """Fixed safe validation errors; never include supplied values."""


def base_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        valid = (isinstance(value, str) and value == value.strip()
                 and not any(ord(char) <= 32 or ord(char) >= 127 for char in value)
                 and "\\" not in value and "?" not in value and "#" not in value
                 and parsed.scheme == "https" and parsed.path == ""
                 and parsed.port in (None, 443) and parsed.username is None and parsed.password is None
                 and host.endswith(".modal.run") and bool(host.removesuffix(".modal.run"))
                 and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                         for label in host.split(".")))
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise Rejected("Use the exact HTTPS Modal base hostname, without a path, query or credentials.")
    return value


def limits(wall_seconds: float, max_redirects: int) -> None:
    if not 0 < wall_seconds <= MAX_WALL_SECONDS or not 0 <= max_redirects <= MAX_REDIRECTS:
        raise Rejected("Health checks allow at most 960 seconds and six 303 continuations.")


def build_plan(base: str = DEFAULT_BASE, *, wall_seconds: float = MAX_WALL_SECONDS,
               max_redirects: int = MAX_REDIRECTS) -> dict:
    base = base_url(base)
    limits(wall_seconds, max_redirects)
    return {"schema_version": 1, "record_type": "modal_readiness_plan", "plan_only": True,
            "network_requests_made": 0, "endpoint_sha256": hashlib.sha256(base.encode()).hexdigest(),
            "method": "GET", "path": "/health", "logical_requests": 1,
            "limits": {"wall_seconds": wall_seconds, "same_request_303_continuations": max_redirects,
                       "maximum_http_requests": 1 + max_redirects, "automatic_failure_retries": 0},
            "cost": "A health request can start billable GPU loading; execution needs an explicit cost acknowledgement.",
            "privacy": "Credentials and continuation queries are never written to the result.",
            "measurement": "Readiness only; no model inference or speech API request."}


def private_work_path(path: Path, *, root: Path = ROOT, existing: bool) -> Path:
    work = root.resolve() / "work"
    candidate = path if path.is_absolute() else root.resolve() / path
    if ".." in path.parts or not candidate.is_relative_to(work) or candidate == work:
        raise Rejected("Use a JSON file strictly inside the ignored work directory.")
    if candidate.suffix.lower() != ".json":
        raise Rejected("Use a JSON file strictly inside the ignored work directory.")
    for part in (candidate, *candidate.parents):
        if part.is_relative_to(work) and (part.is_symlink() or bool(getattr(part, "is_junction", lambda: False)())):
            raise Rejected("Linked work files are not supported.")
    if not candidate.resolve().is_relative_to(work.resolve()):
        raise Rejected("Use a JSON file strictly inside the ignored work directory.")
    if existing and not candidate.is_file() or not existing and candidate.exists():
        raise Rejected("The private input must exist and the result file must be new.")
    return candidate


def authentication(credentials: dict) -> dict[str, str]:
    if (not isinstance(credentials, dict) or set(credentials) != CREDENTIAL_KEYS
            or any(not isinstance(value, str) or not re.fullmatch(r"[!-~]{1,4096}", value)
                   for value in credentials.values())):
        raise Rejected("The private credentials file must contain the three complete authentication values.")
    return {"Authorization": "Bearer " + credentials["api_key"],
            "Modal-Key": credentials["modal_key"], "Modal-Secret": credentials["modal_secret"]}


def load_credentials(path: Path, *, root: Path = ROOT) -> dict:
    path = private_work_path(path, root=root, existing=True)
    if path.stat().st_size > 16384:
        raise Rejected("The private credentials file is invalid.")
    try:
        credentials = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise Rejected("The private credentials file is invalid.") from None
    authentication(credentials)
    return credentials


def continuation_url(base: str, current: str, location: str | None) -> str:
    if (not isinstance(location, str) or not location or len(location) > 16384
            or any(ord(char) <= 32 or ord(char) >= 127 for char in location)
            or "\\" in location or "#" in location):
        raise Rejected("The health continuation destination was rejected.")
    try:
        target = urljoin(current, location)
        parsed, origin = urlsplit(target), urlsplit(base)
        valid = (parsed.scheme == "https" and parsed.hostname == origin.hostname
                 and parsed.port in (None, 443) and parsed.username is None and parsed.password is None
                 and parsed.path == "/health" and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise Rejected("The health continuation destination was rejected.")
    return target


async def check_readiness(base: str, credentials: dict, *, wall_seconds: float = MAX_WALL_SECONDS,
                          max_redirects: int = MAX_REDIRECTS, transport=None, clock=None) -> dict:
    """One health request and only its same-origin, same-path 303 continuations."""
    import httpx

    plan = build_plan(base, wall_seconds=wall_seconds, max_redirects=max_redirects)
    headers = authentication(credentials)
    clock = time.monotonic if clock is None else clock
    started = clock()
    result = {"schema_version": 1, "record_type": "modal_readiness_result",
              "endpoint_sha256": plan["endpoint_sha256"], "ready": False,
              "failure_class": None, "status_history": [], "http_requests": 0,
              "followed_303_continuations": 0, "automatic_failure_retries": 0,
              "wall_seconds": None, "inference_requests": 0, "speech_requests": 0}
    current = base + "/health"
    try:
        async with asyncio.timeout(wall_seconds):
            async with httpx.AsyncClient(transport=transport, follow_redirects=False, trust_env=False) as client:
                while True:
                    remaining = wall_seconds - (clock() - started)
                    if remaining <= 0:
                        raise TimeoutError
                    result["http_requests"] += 1
                    async with client.stream("GET", current, headers=headers, timeout=remaining,
                                             follow_redirects=False) as response:
                        result["status_history"].append({"status_code": response.status_code,
                            "elapsed_ms": round(max(0, clock() - started) * 1000, 3)})
                        if response.status_code == 200:
                            result["ready"] = True
                            break
                        if response.status_code != 303:
                            result["failure_class"] = "http_status"
                            break
                        if result["followed_303_continuations"] >= max_redirects:
                            result["failure_class"] = "continuation_limit"
                            break
                        try:
                            following = continuation_url(base, current, response.headers.get("location"))
                        except Rejected:
                            result["failure_class"] = "continuation_destination"
                            break
                    current = following
                    result["followed_303_continuations"] += 1
    except (TimeoutError, httpx.TimeoutException):
        result["failure_class"] = "timeout"
    except httpx.RequestError:
        result["failure_class"] = "request_failed"
    result["wall_seconds"] = round(max(0, clock() - started), 3)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--acknowledge-gpu-cost", action="store_true")
    parser.add_argument("--credentials-file", type=Path, default=ROOT / "work/modal-private/client.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--wall-seconds", type=float, default=MAX_WALL_SECONDS)
    parser.add_argument("--max-redirects", type=int, default=MAX_REDIRECTS)
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args.base_url, wall_seconds=args.wall_seconds, max_redirects=args.max_redirects)
        if not args.run:
            print(json.dumps(plan, indent=2, allow_nan=False))
            return 0
        if not args.acknowledge_gpu_cost or "replace" in args.base_url.lower():
            raise Rejected("Execution needs the deployed hostname and --acknowledge-gpu-cost.")
        output = private_work_path(args.output, existing=False) if args.output else None
        credentials = load_credentials(args.credentials_file)
        report = asyncio.run(check_readiness(args.base_url, credentials, wall_seconds=args.wall_seconds,
                                            max_redirects=args.max_redirects))
        encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as destination:
                destination.write(encoded)
        print(encoded, end="")
        return 0 if report["ready"] else 1
    except (Rejected, OSError):
        print("Readiness was not run or could not be recorded; verify the approved hostname and private local files.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
