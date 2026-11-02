"""Explicit Modal deployment; import constructs lazy handles but downloads no model.

Requires a reviewed UTC MODAL_EVON_SESSION_EXPIRES_AT at most two hours ahead.
Use the isolated Modal CLI only after checking the workspace's credit/spend limits.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILE = ROOT / "scripts" / "modal_evon_runtime.py"
INPUTS_FILE = ROOT / "deploy" / "evon" / "inputs.verified-2026-10-28.json"
PINS_FILE = ROOT / "deploy" / "evon" / "pins.verified-2026-10-28.json"
runtime_spec = importlib.util.spec_from_file_location("artha_modal_runtime_config", RUNTIME_FILE)
runtime = importlib.util.module_from_spec(runtime_spec)
runtime_spec.loader.exec_module(runtime)
runtime.validate_controller_python()
CONFIG = json.loads(INPUTS_FILE.read_text(encoding="utf-8"))
PINS = json.loads(PINS_FILE.read_text(encoding="utf-8"))
runtime.validate_inputs(CONFIG, PINS)
SESSION_EXPIRES_AT = os.environ.get("MODAL_EVON_SESSION_EXPIRES_AT")
runtime.parse_expiry(SESSION_EXPIRES_AT, require_minimum=True)

APP_NAME = "artha-evon-test"
ALLOCATION = json.loads((ROOT / "deploy" / "modal" / "allocation.json").read_text())
REGION = ALLOCATION["region"]  # Temporary Asia hosting; not India-only residency.
ROUTING_REGION = "ap-south"
app = modal.App(APP_NAME, include_source=False)
weights = modal.Volume.from_name("artha-evon-weights-v2", create_if_missing=True, version=2)
inference_secret = modal.Secret.from_name("artha-evon-inference", required_keys=["VLLM_API_KEY"])
image = (modal.Image.from_registry(CONFIG["image"], setup_dockerfile_commands=[
             # The pinned image has python3 + pip, but no `python` command for Modal.
             "RUN ln -s /usr/bin/python3 /usr/local/bin/python",
             "RUN python --version && python -m pip --version",
         ])
         .entrypoint([])
         .add_local_file(RUNTIME_FILE, "/opt/artha/modal_evon_runtime.py", copy=False)
         .add_local_file(INPUTS_FILE, "/opt/artha/evon-inputs.json", copy=False)
         .add_local_file(PINS_FILE, "/opt/artha/evon-pins.json", copy=False))


@app.function(image=image, serialized=True, include_source=False, region=REGION,
              cpu=(2, 2), memory=(4096, 4096), timeout=1800, retries=0,
              min_containers=0, max_containers=1, buffer_containers=0, scaledown_window=30,
              volumes={"/models": weights}, env={"MODAL_EVON_SESSION_EXPIRES_AT": SESSION_EXPIRES_AT,
              "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"})
def download_weights():
    """Call explicitly once on CPU after approval; deployment itself never calls it."""
    import json
    import os
    from pathlib import Path
    import sys
    import modal

    sys.path.insert(0, "/opt/artha")
    from modal_evon_runtime import prepare_cache

    config = json.loads(Path("/opt/artha/evon-inputs.json").read_text())
    pins = json.loads(Path("/opt/artha/evon-pins.json").read_text())
    volume = modal.Volume.from_name("artha-evon-weights-v2", version=2)
    volume.reload()
    return prepare_cache(config, pins, os.environ["MODAL_EVON_SESSION_EXPIRES_AT"], commit=volume.commit)


@app.function(image=image, serialized=True, include_source=False, gpu=ALLOCATION["gpu"], region=REGION,
              routing_region=ROUTING_REGION,
              cpu=(ALLOCATION["cpu_cores"], ALLOCATION["cpu_cores"]),
              memory=(ALLOCATION["memory_gib"] * 1024, ALLOCATION["memory_gib"] * 1024), timeout=7200,
              startup_timeout=900, min_containers=0, max_containers=ALLOCATION["max_containers"],
              # Bounded stage handoff lease; min=0 and the absolute expiry still apply.
              buffer_containers=0, scaledown_window=300, secrets=[inference_secret],
              volumes={"/models": weights.with_mount_options(read_only=True)},
              env={"MODAL_EVON_SESSION_EXPIRES_AT": SESSION_EXPIRES_AT,
                   "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "OMP_NUM_THREADS": "4"})
@modal.web_server(port=8000, startup_timeout=900, requires_proxy_auth=True)
def serve():
    import json
    import os
    from pathlib import Path
    import sys

    sys.path.insert(0, "/opt/artha")
    from modal_evon_runtime import start_server

    config = json.loads(Path("/opt/artha/evon-inputs.json").read_text())
    pins = json.loads(Path("/opt/artha/evon-pins.json").read_text())
    start_server(config, pins, os.environ["MODAL_EVON_SESSION_EXPIRES_AT"])
