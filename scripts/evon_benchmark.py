"""Offline-first, bounded text-only Evon acceptance runner. Never reads .env.

Execution requires an exact plan hash plus explicit acknowledgement of GPU cost.
Run plans and reports are separate from the application's speech usage ledger.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import importlib.util
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
_prompt_spec = importlib.util.spec_from_file_location("evon_pure_prompt", ROOT / "server/charcha/providers/translation_prompt.py")
_prompt = importlib.util.module_from_spec(_prompt_spec)
_prompt_spec.loader.exec_module(_prompt)
PROMPT_VERSION = _prompt.PROMPT_VERSION
DEFAULT_CORPUS = ROOT / "evaluation" / "everyday_cases.jsonl"
MODEL = "gnani/gnani-evon-v3.3-30B-A3B"
LANGUAGES = {"hi": "Hindi", "ta": "Tamil", "bn": "Bengali", "en": "English",
             "te": "Telugu", "mr": "Marathi", "gu": "Gujarati", "kn": "Kannada",
             "ml": "Malayalam", "pa": "Punjabi", "or": "Odia"}
REASONING_MARKER = re.compile(
    r"</?(?:think|thinking|analysis|reasoning)(?=[\s>])|<\|(?:analysis|assistant|im_start|im_end)\|>",
    re.IGNORECASE,
)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def endpoint_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Endpoint must not contain credentials, query parameters or fragments")
    if not parsed.hostname or parsed.scheme not in {"http", "https"}:
        raise ValueError("Provide an HTTPS base URL or an HTTP loopback SSH tunnel")
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname == "localhost"
    if parsed.scheme == "http" and not loopback:
        raise ValueError("Remote endpoints require HTTPS; prefer a loopback SSH tunnel")
    # Accessing port validates malformed/out-of-range ports before any network work.
    _ = parsed.port
    return value.rstrip("/")


def modal_proxy_headers(endpoint: str, key: str = "", secret: str = "") -> dict[str, str]:
    """Standalone equivalent of the adapter guard; never imports app settings."""
    if not key and not secret:
        return {}
    if not key or not secret or any(
        len(value) > 4096 or any(not 33 <= ord(char) <= 126 for char in value)
        for value in (key, secret)
    ):
        raise ValueError("Invalid proxy authentication configuration")
    parsed = urlsplit(endpoint)
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or not host.endswith(".modal.run")
            or not host.removesuffix(".modal.run") or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Invalid proxy authentication destination")
    return {"Modal-Key": key, "Modal-Secret": secret}


def load_cases(path: Path, selected: list[str] | None) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {row["id"]: row for row in rows}
    if len(rows) != len(by_id):
        raise ValueError("Corpus case IDs must be unique")
    wanted = selected or ["hi-ta-01", "ta-hi-01"]
    if not 1 <= len(wanted) <= 18 or len(wanted) != len(set(wanted)):
        raise ValueError("Choose 1–18 distinct case IDs")
    cases = []
    for case_id in wanted:
        if case_id not in by_id:
            raise ValueError("Requested case ID is absent from the corpus")
        row = by_id[case_id]
        if row["source_language"] not in LANGUAGES or row["target_language"] not in LANGUAGES:
            raise ValueError("Unsupported case language")
        if not isinstance(row["source_text"], str) or not 1 <= len(row["source_text"]) <= 2000:
            raise ValueError("Case source text must contain 1–2000 characters")
        cases.append({key: row[key] for key in (
            "id", "source_language", "target_language", "source_text", "reference_draft",
            "reference_status", "critical_values", "review_focus")})
    return cases


def build_plan(cases: list[dict], *, endpoint: str = "http://127.0.0.1:8001/v1",
               model: str = MODEL, max_tokens: int = 256, timeout: float = 30,
               wall_seconds: float = 120) -> dict:
    endpoint = endpoint_url(endpoint)
    if not re.fullmatch(r"[A-Za-z0-9_./:-]{1,200}", model):
        raise ValueError("Invalid served model name")
    if not 1 <= len(cases) <= 18 or not 1 <= max_tokens <= 512:
        raise ValueError("At most 18 requests and 512 output tokens per request")
    if not 1 <= timeout <= 60 or not timeout <= wall_seconds <= 600:
        raise ValueError("Timeout must be 1–60 seconds; wall limit timeout–600 seconds")
    plan = {
        "schema_version": 1, "kind": "evon_text_acceptance", "plan_only": True,
        "provider_calls_made": 0, "model": model,
        "prompt_version": PROMPT_VERSION,
        "endpoint_sha256": hashlib.sha256(endpoint.encode()).hexdigest(),
        "limits": {"requests": len(cases), "output_tokens_per_request": max_tokens,
                   "request_timeout_seconds": timeout, "wall_seconds": wall_seconds,
                   "automatic_retries": 0},
        "speech": {"stt": False, "tts": False, "voice_cloning": False},
        "cost": {"gpu_runtime": "billable while the rented VM runs, including startup/idle",
                 "provider_actual_charge": None, "programme_credit_conversion": None},
        "measurement": "client request start to complete translation response; not first token or audio latency",
        "meaning_acceptance": "manual bilingual review required; drafts are not ground truth",
        "cases": cases,
    }
    plan["plan_sha256"] = digest(plan)
    return plan


def request_body(plan: dict, case: dict) -> dict:
    return {"model": plan["model"], "messages": _prompt.translation_messages(
        case["source_text"], case["source_language"], case["target_language"]),
        "temperature": 0.0, "max_tokens": plan["limits"]["output_tokens_per_request"],
        "stream": False, "chat_template_kwargs": {"enable_thinking": False}}


def completed_translation(payload: object) -> str:
    """Mirror the application's contract without importing its settings/providers.

    Contract-parity tests keep the standalone no-.env runner aligned with the app.
    """
    if not isinstance(payload, dict):
        raise ValueError("invalid_response")
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("invalid_response")
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
        raise ValueError("incomplete_response")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role", "assistant") != "assistant":
        raise ValueError("invalid_response")
    if (message.get("tool_calls") or message.get("function_call") or message.get("refusal")
            or message.get("reasoning_content") not in (None, "")
            or message.get("reasoning") not in (None, "")):
        raise ValueError("unexpected_channel")
    translated = message.get("content")
    if (not isinstance(translated, str) or not translated.strip() or len(translated) > 8000
            or REASONING_MARKER.search(translated)):
        raise ValueError("invalid_translation")
    return translated.strip()


def authorize(plan: dict, approved_hash: str | None, acknowledge_cost: bool) -> None:
    if plan.get("prompt_version") != PROMPT_VERSION:
        raise ValueError("Create a new plan for the current translation prompt version")
    unsigned = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if digest(unsigned) != plan.get("plan_sha256"):
        raise ValueError("Plan content changed after hashing")
    if not acknowledge_cost or approved_hash != plan["plan_sha256"]:
        raise ValueError("Execution needs --acknowledge-gpu-cost and --approve-plan matching the reviewed plan")


async def execute(plan: dict, endpoint: str, approved_hash: str | None, acknowledge_cost: bool,
                  *, api_key: str, transport=None, modal_key: str = "", modal_secret: str = "") -> dict:
    authorize(plan, approved_hash, acknowledge_cost)
    endpoint = endpoint_url(endpoint)
    if hashlib.sha256(endpoint.encode()).hexdigest() != plan["endpoint_sha256"]:
        raise ValueError("Endpoint differs from the approved plan")
    if not api_key or len(api_key) < 16 or any(c.isspace() for c in api_key):
        raise ValueError("Set a private EVON_BENCHMARK_API_KEY of at least 16 characters")
    headers = {"Authorization": "Bearer " + api_key}
    headers.update(modal_proxy_headers(endpoint, modal_key, modal_secret))
    # Imported only after approval. No application settings, .env or provider SDKs.
    import httpx

    started = time.perf_counter()
    report = {"schema_version": 1, "kind": "evon_text_acceptance_result",
              "plan_sha256": plan["plan_sha256"], "model": plan["model"],
              "provider_calls_attempted": 0, "speech_provider_calls": 0,
              "actual_charge": None, "programme_credit_conversion": None,
              "measurement": plan["measurement"], "meaning_acceptance": "not_reviewed",
              "stopped_on_error": False, "results": []}
    async with httpx.AsyncClient(transport=transport, follow_redirects=False, trust_env=False,
                                 headers=headers) as client:
        for case in plan["cases"]:
            remaining = plan["limits"]["wall_seconds"] - (time.perf_counter() - started)
            if remaining <= 0:
                report["stop_reason"] = "wall_limit"
                break
            timeout = min(plan["limits"]["request_timeout_seconds"], remaining)
            row = {"case_id": case["id"], "source_language": case["source_language"],
                   "target_language": case["target_language"], "meaning_review": "pending",
                   "status": "failed", "latency_ms": None}
            attempt = time.perf_counter()
            report["provider_calls_attempted"] += 1
            try:
                # HTTP timeout alone is per I/O operation. asyncio bounds the whole request.
                async with asyncio.timeout(timeout):
                    async with client.stream("POST", endpoint + "/chat/completions",
                                             json=request_body(plan, case), timeout=timeout) as response:
                        response.raise_for_status()
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > 131072:
                                raise ValueError("oversized_response")
                payload = json.loads(content)
                translated = completed_translation(payload)
                _prompt.check_target_script(translated, case["target_language"])
                # Never export a reflected credential, even from a faulty endpoint.
                translated = translated.strip()
                for credential in sorted((value for value in (api_key, modal_key, modal_secret) if value), key=len, reverse=True):
                    translated = translated.replace(credential, "[REDACTED]")
                row.update(status="response_received", translation=translated,
                           numeric_presence={number: number in translated for number in case["critical_values"]["numeric"]})
            except httpx.HTTPStatusError as exc:
                row["error"] = "http_error"
                row["http_status"] = exc.response.status_code
            except (httpx.TimeoutException, TimeoutError):
                row["error"] = "timeout"
            except httpx.HTTPError:
                row["error"] = "transport_error"
            except (ValueError, KeyError, IndexError, TypeError, UnicodeError):
                row["error"] = "invalid_or_incomplete_response"
            row["latency_ms"] = round((time.perf_counter() - attempt) * 1000, 3)
            report["results"].append(row)
            if row["status"] == "failed":
                report["stopped_on_error"] = True
                report["stop_reason"] = row["error"]
                break
    report["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    report["unattempted_cases"] = len(plan["cases"]) - report["provider_calls_attempted"]
    report["complete"] = report["unattempted_cases"] == 0 and not report["stopped_on_error"]
    report["note"] = "Response received is not semantic acceptance. Numeric presence does not verify associations or negation. VM billing continues until stopped separately."
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=lambda prog: argparse.HelpFormatter(prog, width=88))
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--wall-seconds", type=float, default=120)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approve-plan")
    parser.add_argument("--acknowledge-gpu-cost", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.exists():
            raise ValueError("Output already exists; choose a new filename")
        plan = build_plan(load_cases(args.corpus, args.cases), endpoint=args.endpoint, model=args.model,
                          max_tokens=args.max_tokens, timeout=args.timeout, wall_seconds=args.wall_seconds)
        result = plan
        if args.execute:
            authorize(plan, args.approve_plan, args.acknowledge_gpu_cost)
            result = asyncio.run(execute(plan, args.endpoint, args.approve_plan, args.acknowledge_gpu_cost,
                                         api_key=os.environ.get("EVON_BENCHMARK_API_KEY", ""),
                                         modal_key=os.environ.get("EVON_BENCHMARK_MODAL_KEY", ""),
                                         modal_secret=os.environ.get("EVON_BENCHMARK_MODAL_SECRET", "")))
        encoded = json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
        else:
            print(encoded)
        return 0 if not args.execute or result["complete"] else 1
    except (ValueError, OSError, KeyError, TypeError):
        # Avoid printing raw exception strings that may include user paths or secrets.
        print("Invalid plan, approval, credentials or output path. Review --help and docs/GPU_TESTING.md.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
