"""Generate a portable, non-secret Evon Compose file offline. Never starts Docker."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def build_compose(config: dict) -> dict:
    if not re.fullmatch(r"vllm/vllm-openai@sha256:[a-f0-9]{64}", config.get("image", "")):
        raise ValueError("Use a verified immutable vLLM image digest")
    if not re.fullmatch(r"[a-f0-9]{40}", config.get("model_revision", "")):
        raise ValueError("Use the verified full Hugging Face model commit")
    if config.get("model") != "gnani/gnani-evon-v3.3-30B-A3B":
        raise ValueError("This profile is reviewed only for the specified Evon repository")
    if config.get("trust_remote_code") is not False:
        raise ValueError("This native Nemotron profile must keep remote-code execution disabled")
    if config.get("platform") != "linux/amd64":
        raise ValueError("The verified image profile is Linux AMD64")
    port = config.get("port", 8001)
    if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
        raise ValueError("Choose an unprivileged local port")
    return {"name": "artha-evon-test", "services": {"evon": {
        "image": config["image"], "platform": "linux/amd64", "restart": "no", "ipc": "host",
        "env_file": [{"path": "credentials.env", "format": "raw", "required": True}],
        "environment": {"VLLM_NO_USAGE_STATS": "1", "DO_NOT_TRACK": "1", "HF_HUB_DISABLE_TELEMETRY": "1"},
        "ports": [f"127.0.0.1:{port}:8000"],
        "volumes": ["evon-models:/root/.cache/huggingface"],
        "entrypoint": ["/bin/sh", "-ec", (
            '[ "$${#VLLM_API_KEY}" -ge 32 ] && [ "$$VLLM_API_KEY" != "REPLACE_WITH_PRIVATE_RANDOM_SECRET" ] '
            '|| { echo "Set a private VLLM_API_KEY of at least 32 characters"; exit 1; }; '
            'exec python3 -m vllm.entrypoints.openai.api_server "$$@"'), "evon"],
        "command": ["--model", config["model"], "--revision", config["model_revision"],
                    "--tokenizer-revision", config["model_revision"], "--served-model-name", config["model"],
                    "--dtype", "bfloat16", "--max-model-len", "4096",
                    "--max-num-seqs", "2", "--generation-config", "vllm",
                    "--host", "0.0.0.0", "--port", "8000"],
        "deploy": {"resources": {"reservations": {"devices": [
            {"driver": "nvidia", "count": 1, "capabilities": ["gpu"]}]}}},
        "healthcheck": {"test": ["CMD", "python3", "-c",
                        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"],
                        "interval": "15s", "timeout": "5s", "retries": 3, "start_period": "15m"},
    }}, "volumes": {"evon-models": {}}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", default=Path("work/evon/compose.json"), type=Path)
    args = parser.parse_args(argv)
    try:
        compose = build_compose(json.loads(args.config.read_text(encoding="utf-8")))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(compose, stream, indent=2)
            stream.write("\n")
        print("Prepared non-secret Compose configuration. Nothing downloaded or started.")
        return 0
    except (ValueError, OSError, TypeError):
        print("Preparation failed: verify pinned inputs and choose a new output path. See docs/GPU_TESTING.md.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
