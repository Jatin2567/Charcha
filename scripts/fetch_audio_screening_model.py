"""Explicit free download of a checksum-pinned, MIT AASIST ONNX artifact.

This utility downloads model data and its licence only. It never imports upstream
code, loads pickle, starts a server, or sends audio. Runtime screening is offline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

REVISION = "16774d458d86d2a021ae31646c1bf66a5331b53e"
MODEL_ID = "SpeechAntiSpoofingBenchmarks/AASIST"
SHA256 = "130e536266b7c537f9a13029e1612a9f392fd1cc827783683b6d1c062a3db5e1"
BASE = f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}"
DEFAULT = Path(__file__).resolve().parents[1] / "server" / "models" / "aasist"


def bounded_download(url: str, limit: int) -> bytes:
    with urlopen(url, timeout=45) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Artifact exceeds expected download size")
    return data


def fetch(destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "model.onnx"
    if target.exists() and target.stat().st_size <= 4_000_000:
        data = target.read_bytes()
    else:
        data = b""
    if hashlib.sha256(data).hexdigest() != SHA256:
        data = bounded_download(BASE + "/aasist.onnx", 4_000_000)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("AASIST artifact checksum mismatch; nothing installed")
    license_data = bounded_download(BASE + "/LICENSE", 20_000)
    if b"NAVER" not in license_data or b"Permission is hereby granted" not in license_data:
        raise ValueError("Expected MIT licence missing; nothing installed")
    temporary = destination / "model.onnx.download"
    temporary.write_bytes(data)
    temporary.replace(target)
    (destination / "LICENSE").write_bytes(license_data)
    manifest = {
        "id": MODEL_ID, "revision": REVISION, "sha256": SHA256,
        "bytes": len(data), "license": "MIT", "format": "ONNX",
        "source": BASE + "/aasist.onnx", "sample_rate": 16000,
        "window_samples": 64600, "labels": {"0": "spoof", "1": "bonafide"},
        "experimental": True, "validated_on_indian_meeting_audio": False,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT)
    args = parser.parse_args()
    print(json.dumps(fetch(args.directory), indent=2))
