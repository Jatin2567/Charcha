"""Bounded Modal Evon lifecycle helpers. Importing this module performs no I/O."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

MAX_SESSION_SECONDS = 7200
STARTUP_SECONDS = 900
DOWNLOAD_SECONDS = 1800
KILL_SIGNAL = getattr(signal, "SIGKILL", 9)  # POSIX signal used only in the Linux container.
CACHE_ROOT = Path("/models")
MODEL = "gnani/gnani-evon-v3.3-30B-A3B"
CONTROLLER_PYTHON = (3, 12)
METADATA_FILES = {
    "model-config.json": "config.json",
    "tokenizer-config.json": "tokenizer_config.json",
    "model-index.json": "model.safetensors.index.json",
}


def validate_controller_python(version=None) -> None:
    """Serialized functions must match the pinned image's Python minor version."""
    version = sys.version_info if version is None else version
    if tuple(version[:2]) != CONTROLLER_PYTHON:
        raise ValueError("Deploy with Python 3.12: the pinned image and serialized functions require the same minor version")


def parse_expiry(value: object, *, now: float | None = None, require_minimum: bool = False) -> float:
    """Require one absolute UTC deadline; restarting a container cannot renew it."""
    now = time.time() if now is None else now
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Set MODAL_EVON_SESSION_EXPIRES_AT to an absolute UTC timestamp")
    try:
        expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Session expiry must be an ISO UTC timestamp") from None
    if expiry.tzinfo is None or expiry.utcoffset().total_seconds() != 0:
        raise ValueError("Session expiry must include UTC Z or +00:00")
    seconds = expiry.timestamp() - now
    if not 0 < seconds <= MAX_SESSION_SECONDS:
        raise ValueError("Session is expired or more than two hours away")
    if require_minimum and seconds < 60:
        raise ValueError("Allow at least 60 seconds before deployment expires")
    return expiry.timestamp()


def validate_inputs(config: dict, pins: dict) -> None:
    if (not isinstance(config, dict) or config.get("model") != MODEL
            or not re.fullmatch(r"[a-f0-9]{40}", str(config.get("model_revision", "")))
            or not re.fullmatch(r"vllm/vllm-openai@sha256:[a-f0-9]{64}", str(config.get("image", "")))
            or config.get("trust_remote_code") is not False
            or config.get("platform") != "linux/amd64"):
        raise ValueError("Use the reviewed native Evon inputs")
    if (pins.get("model", {}).get("revision") != config["model_revision"]
            or pins.get("model", {}).get("repository") != MODEL
            or pins.get("runtime", {}).get("image") != config["image"]):
        raise ValueError("Metadata pins do not match deployment inputs")


def snapshot_path(config: dict, cache_root: Path = CACHE_ROOT) -> Path:
    return cache_root / "hf" / "models--gnani--gnani-evon-v3.3-30B-A3B" / "snapshots" / config["model_revision"]


def inspect_cache(config: dict, pins: dict, cache_root: Path = CACHE_ROOT) -> dict:
    """Check pinned metadata and complete shard files; this is not a tensor hash audit."""
    validate_inputs(config, pins)
    snapshot = snapshot_path(config, cache_root)
    expected = {row["file"]: row["sha256"] for row in pins["source_files"] if row["file"] in METADATA_FILES}
    if set(expected) != set(METADATA_FILES):
        raise ValueError("Pinned metadata hashes are incomplete")
    for source, filename in METADATA_FILES.items():
        path = snapshot / filename
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected[source]:
            raise ValueError("Cached metadata is absent or differs from the pinned revision")
    model_config = json.loads((snapshot / "config.json").read_text())
    tokenizer_config = json.loads((snapshot / "tokenizer_config.json").read_text())
    if (model_config.get("architectures") != ["NemotronHForCausalLM"]
            or model_config.get("auto_map") or tokenizer_config.get("auto_map")):
        raise ValueError("Cached model requires an unreviewed architecture or remote code")
    index = json.loads((snapshot / "model.safetensors.index.json").read_text())
    total = pins["model"]["tensor_bytes_from_index"]
    if index.get("metadata", {}).get("total_size") != total:
        raise ValueError("Cached tensor index size differs from reviewed metadata")
    filenames = sorted(set(index["weight_map"].values()))
    if len(filenames) != 13 or any(not re.fullmatch(r"model-\d{5}-of-00013\.safetensors", name) for name in filenames):
        raise ValueError("Unexpected model shard manifest")
    sizes = []
    for filename in filenames:
        path = snapshot / filename
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError("Cached model shards are incomplete; run CPU download first")
        sizes.append(path.stat().st_size)
    if sum(sizes) < total:
        raise ValueError("Cached shard files are shorter than the indexed tensor data")
    if not (snapshot / "tokenizer.json").is_file():
        raise ValueError("Cached tokenizer is incomplete")
    return {"schema_version": 1, "repository": MODEL, "revision": config["model_revision"],
            "metadata_sha256": expected, "shard_count": len(filenames),
            "shard_file_bytes": sum(sizes), "tensor_bytes_from_index": total,
            "verification": "pinned metadata hashes, shard presence and sizes; not independent tensor hashes"}


def require_cache(config: dict, pins: dict, cache_root: Path = CACHE_ROOT) -> Path:
    marker = cache_root / "artha-evon-cache.json"
    if not marker.is_file():
        raise ValueError("CPU model preparation has not committed a cache marker")
    report = inspect_cache(config, pins, cache_root)
    if json.loads(marker.read_text()) != report:
        raise ValueError("Model cache marker is stale or does not match the pinned files")
    return snapshot_path(config, cache_root)


def prepare_cache(config: dict, pins: dict, expires_at: str, *, cache_root: Path = CACHE_ROOT,
                  runner=None, commit=None, now=None, environment=None) -> dict:
    """Explicit CPU-only operation. Never called by import, build, deploy or GPU serve."""
    now = time.time if now is None else now
    expiry = parse_expiry(expires_at, now=now())
    validate_inputs(config, pins)
    runner = subprocess.run if runner is None else runner
    code = (
        "import sys; from huggingface_hub import snapshot_download; "
        "snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2], cache_dir=sys.argv[3], "
        "allow_patterns=['*.json','*.safetensors','*.model','*.tiktoken','*.txt','*.jinja','*.jinja2'], "
        "ignore_patterns=['*.py','*.bin','*.pt','*.pth'], max_workers=4)"
    )
    timeout = min(DOWNLOAD_SECONDS, expiry - now())
    if timeout <= 0:
        raise ValueError("Session expired before CPU download")
    # Select the reviewed HTTP path explicitly. A fresh child must read these
    # before huggingface_hub is imported; changing os.environ here could affect
    # unrelated work in the controller. There is no automatic transport retry.
    child_environment = dict(os.environ if environment is None else environment)
    child_environment.update({"HF_HUB_DISABLE_XET": "1", "HF_HUB_DISABLE_SHARED_BLOBS": "1",
                              "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"})
    # A subprocess timeout can stop the download worker; a Python thread timeout cannot.
    runner([sys.executable, "-c", code, MODEL, config["model_revision"], str(cache_root / "hf")],
           check=True, timeout=timeout, shell=False, env=child_environment)
    parse_expiry(expires_at, now=now())
    report = inspect_cache(config, pins, cache_root)
    marker = cache_root / "artha-evon-cache.json"
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(marker)
    if commit is not None:
        commit()
    return report


def check_gpu(*, runner=None) -> dict:
    runner = subprocess.run if runner is None else runner
    result = runner(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=10, check=True, shell=False)
    rows = [row.strip() for row in result.stdout.splitlines() if row.strip()]
    if len(rows) != 1:
        raise ValueError("The reviewed profile requires exactly one visible GPU")
    fields = [field.strip() for field in rows[0].split(",")]
    if len(fields) != 3 or not re.fullmatch(r"\d+(?:\.\d+){1,2}", fields[2]):
        raise ValueError("GPU facts could not be verified")
    try:
        memory_mib = int(fields[1])
    except ValueError:
        raise ValueError("GPU memory could not be verified") from None
    if memory_mib < 76000 or int(fields[2].split(".")[0]) < 580 or not any(g in fields[0] for g in ("A100", "H100")):
        raise ValueError("GPU must be an A100 80 GB with R580+ for the pinned CUDA 13 image")
    return {"gpu": fields[0], "memory_mib": memory_mib, "driver": fields[2]}


def validate_api_key(value: object) -> str:
    if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", value)
            or value.startswith("vach_") or "REPLACE" in value.upper()):
        raise ValueError("Use a separate random VLLM_API_KEY of 32â€“256 URL-safe characters")
    return value


def server_command(config: dict, local_model: Path) -> list[str]:
    # The server key comes only from VLLM_API_KEY; no credential is present in argv.
    return ["python3", "-m", "vllm.entrypoints.openai.api_server", "--model", str(local_model),
            "--tokenizer", str(local_model), "--revision", config["model_revision"],
            "--tokenizer-revision", config["model_revision"], "--served-model-name", MODEL,
            "--dtype", "bfloat16", "--max-model-len", "4096", "--max-num-seqs", "2",
            "--generation-config", "vllm", "--no-enable-log-requests", "--no-enable-log-outputs",
            "--no-trust-request-chat-template", "--disable-fastapi-docs", "--host", "0.0.0.0", "--port", "8000"]


def stop_process(process, *, kill_group=None, wait_seconds: float = 5) -> None:
    """Stop all vLLM workers in the new process group, escalating after a short grace."""
    kill_group = os.killpg if kill_group is None else kill_group
    try:
        kill_group(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=wait_seconds)
    except subprocess.TimeoutExpired:
        pass
    # The parent can exit before a stubborn worker. Clear the whole original
    # process group even when wait() has already observed the parent's exit.
    try:
        kill_group(process.pid, KILL_SIGNAL)
    except ProcessLookupError:
        pass
    process.wait(timeout=wait_seconds)


def deadline_watchdog(process, expiry: float, cancelled, *, now=None, monotonic=None, stop=None) -> None:
    now = time.time if now is None else now
    monotonic = time.monotonic if monotonic is None else monotonic
    stop = stop_process if stop is None else stop
    monotonic_end = monotonic() + max(0, expiry - now())
    while not cancelled.is_set():
        remaining = min(expiry - now(), monotonic_end - monotonic())
        if remaining <= 0:
            stop(process)
            return
        if process.poll() is not None:
            stop(process)
            return
        cancelled.wait(min(remaining, 1))


def start_server(config: dict, pins: dict, expires_at: str, *, cache_root: Path = CACHE_ROOT,
                 environment=None, popen=None, urlopen=None, now=None, monotonic=None,
                 sleep=None, thread_factory=None, stopper=None, gpu_check=None, serverless=False):
    """Start only a prepared model, wait for real health, and retain a deadline watchdog."""
    now = time.time if now is None else now
    monotonic = time.monotonic if monotonic is None else monotonic
    expiry = float("inf") if serverless else parse_expiry(expires_at, now=now())
    environment = os.environ if environment is None else environment
    key = validate_api_key(environment.get("VLLM_API_KEY"))
    local_model = require_cache(config, pins, cache_root)
    (check_gpu if gpu_check is None else gpu_check)()
    if not serverless:
        parse_expiry(expires_at, now=now())
    popen = subprocess.Popen if popen is None else popen
    urlopen = urllib.request.urlopen if urlopen is None else urlopen
    sleep = time.sleep if sleep is None else sleep
    thread_factory = threading.Thread if thread_factory is None else thread_factory
    stopper = stop_process if stopper is None else stopper
    child_environment = dict(environment)
    child_environment.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                              "VLLM_NO_USAGE_STATS": "1", "DO_NOT_TRACK": "1",
                              "HF_HUB_DISABLE_TELEMETRY": "1", "VLLM_LOGGING_LEVEL": "WARNING",
                              "VLLM_DEBUG_LOG_API_SERVER_RESPONSE": "0"})
    process = popen(server_command(config, local_model), env=child_environment,
                    start_new_session=True, shell=False)
    cancelled = threading.Event()
    if not serverless:
        watchdog = thread_factory(target=deadline_watchdog, args=(process, expiry, cancelled),
                                  kwargs={"stop": stopper}, daemon=True, name="evon-fixed-expiry")
        watchdog.start()
    ready_deadline = monotonic() + min(STARTUP_SECONDS, expiry - now())
    request = urllib.request.Request("http://127.0.0.1:8000/health", headers={"Authorization": f"Bearer {key}"})
    try:
        while monotonic() < ready_deadline and now() < expiry:
            if process.poll() is not None:
                raise RuntimeError("Evon stopped before becoming ready; inspect provider logs")
            try:
                with urlopen(request, timeout=min(3, max(0.1, expiry - now()))) as response:
                    if response.status == 200:
                        return process
            except (OSError, urllib.error.URLError):
                pass
            sleep(min(1, max(0, expiry - now())))
        raise TimeoutError("Evon readiness or fixed session deadline elapsed")
    except BaseException:
        cancelled.set()
        stopper(process)
        raise
