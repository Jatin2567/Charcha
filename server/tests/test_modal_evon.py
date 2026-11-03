import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import socket
import subprocess
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("modal_evon_runtime", ROOT / "scripts" / "modal_evon_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc).timestamp()
EXPIRY = "2026-10-28T13:00:00Z"
KEY = "independent_test_key_not_real_1234567890"


@pytest.mark.parametrize("version", [(3, 11), (3, 13), (3, 14)])
def test_serialized_controller_rejects_different_python_minor_before_deployment(version):
    with pytest.raises(ValueError, match="Python 3.12"):
        runtime.validate_controller_python(version)


def test_serialized_controller_accepts_image_python_minor():
    runtime.validate_controller_python((3, 12, 11))


def inputs():
    return json.loads((ROOT / "deploy" / "evon" / "inputs.verified-2026-10-28.json").read_text())


def fake_cache(tmp_path):
    config = inputs()
    directory = runtime.snapshot_path(config, tmp_path)
    directory.mkdir(parents=True)
    files = {
        "model-config.json": {"architectures": ["NemotronHForCausalLM"]},
        "tokenizer-config.json": {"tokenizer_class": "PreTrainedTokenizerFast"},
        "model-index.json": {"metadata": {"total_size": 13}, "weight_map": {
            str(i): f"model-{i:05}-of-00013.safetensors" for i in range(1, 14)}},
    }
    source_files = []
    for source, data in files.items():
        path = directory / runtime.METADATA_FILES[source]
        path.write_text(json.dumps(data), encoding="utf-8")
        source_files.append({"file": source, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    for i in range(1, 14):
        (directory / f"model-{i:05}-of-00013.safetensors").write_bytes(b"x")
    (directory / "tokenizer.json").write_text("{}")
    pins = {"model": {"repository": config["model"], "revision": config["model_revision"],
                      "tensor_bytes_from_index": 13},
            "runtime": {"image": config["image"]}, "source_files": source_files}
    report = runtime.inspect_cache(config, pins, tmp_path)
    (tmp_path / "artha-evon-cache.json").write_text(json.dumps(report))
    return config, pins, directory


@pytest.mark.parametrize("value", [None, "", "tomorrow", "2026-10-28T13:00:00",
                                  "2026-10-28T14:00:00+01:00", "2026-10-28T12:00:00Z",
                                  "2026-10-28T14:00:01Z"])
def test_session_requires_unexpired_absolute_utc_deadline(value):
    with pytest.raises(ValueError):
        runtime.parse_expiry(value, now=NOW)


def test_one_deadline_is_bounded_and_cannot_renew_on_restart():
    assert runtime.parse_expiry(EXPIRY, now=NOW) == NOW + 3600
    assert runtime.parse_expiry(EXPIRY, now=NOW + 3500) == NOW + 3600
    with pytest.raises(ValueError):
        runtime.parse_expiry(EXPIRY, now=NOW + 3600)
    with pytest.raises(ValueError):
        runtime.parse_expiry(EXPIRY, now=NOW + 3590, require_minimum=True)


@pytest.mark.parametrize("value", [None, "short", "REPLACE_WITH_PRIVATE_RANDOM_SECRET", "vach_" + "x" * 40,
                                  "has a space" + "x" * 40, "\n" + "x" * 40])
def test_inference_secret_must_be_private_and_separate_from_gnani(value):
    with pytest.raises(ValueError):
        runtime.validate_api_key(value)
    assert runtime.validate_api_key(KEY) == KEY


def test_cache_has_pinned_metadata_complete_shards_and_marker(tmp_path):
    config, pins, directory = fake_cache(tmp_path)
    assert runtime.require_cache(config, pins, tmp_path) == directory
    (directory / "model-00003-of-00013.safetensors").unlink()
    with pytest.raises(ValueError, match="incomplete"):
        runtime.require_cache(config, pins, tmp_path)


def test_bad_marker_or_changed_metadata_never_becomes_gpu_ready(tmp_path):
    config, pins, directory = fake_cache(tmp_path)
    marker = tmp_path / "artha-evon-cache.json"
    marker.write_text("{}")
    with pytest.raises(ValueError, match="marker"):
        runtime.require_cache(config, pins, tmp_path)
    (directory / "config.json").write_text('{"auto_map": {"model": "untrusted"}}')
    with pytest.raises(ValueError, match="metadata"):
        runtime.inspect_cache(config, pins, tmp_path)


def test_mismatched_revision_and_floating_image_fail_closed(tmp_path):
    config, pins, _ = fake_cache(tmp_path)
    altered = copy.deepcopy(config)
    altered["model_revision"] = "f" * 40
    with pytest.raises(ValueError, match="pins"):
        runtime.validate_inputs(altered, pins)
    altered["image"] = "vllm/vllm-openai:latest"
    with pytest.raises(ValueError, match="reviewed"):
        runtime.validate_inputs(altered, pins)


def test_download_is_separate_bounded_cpu_operation_and_commits_only_complete_cache(tmp_path):
    config, pins, _ = fake_cache(tmp_path)
    calls, commits = [], []

    def run(command, **kwargs):
        calls.append((command, kwargs))

    report = runtime.prepare_cache(config, pins, EXPIRY, cache_root=tmp_path,
                                   runner=run, commit=lambda: commits.append(True), now=lambda: NOW)
    assert len(calls) == 1 and commits == [True]
    command, kwargs = calls[0]
    assert command[3:5] == [config["model"], config["model_revision"]]
    assert "ignore_patterns=['*.py'" in command[2]
    assert "allow_patterns=['*.json','*.safetensors','*.model','*.tiktoken','*.txt','*.jinja','*.jinja2']" in command[2]
    assert "max_workers=4" in command[2]
    assert {key: value for key, value in kwargs.items() if key != "env"} == {
        "check": True, "timeout": 1800, "shell": False}
    assert kwargs["env"]["HF_HUB_DISABLE_XET"] == "1"
    assert kwargs["env"]["HF_HUB_DISABLE_SHARED_BLOBS"] == "1"
    assert report["shard_count"] == 13
    assert "trust_remote_code" not in command[2]


@pytest.mark.parametrize("use_default_environment", [False, True])
def test_cpu_download_selects_http_before_hub_import_without_mutating_parent_environment(
        tmp_path, monkeypatch, use_default_environment):
    config, pins, _ = fake_cache(tmp_path)
    environment = {"PATH": "/reviewed/bin", "HF_HOME": "/retained/cache",
                   "HF_HUB_DISABLE_XET": "0", "HF_HUB_DISABLE_SHARED_BLOBS": "0",
                   "HF_HUB_DISABLE_TELEMETRY": "0", "DO_NOT_TRACK": "0"}
    original = environment.copy()
    calls = []
    if use_default_environment:
        monkeypatch.setattr(runtime.os, "environ", environment)
    runtime.prepare_cache(config, pins, EXPIRY, cache_root=tmp_path,
        runner=lambda command, **kwargs: calls.append((command, kwargs)), now=lambda: NOW,
        **({} if use_default_environment else {"environment": environment}))
    assert environment == original
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:2] == [sys.executable, "-c"]
    assert "from huggingface_hub import snapshot_download" in command[2]
    assert kwargs["env"] is not environment
    assert kwargs["env"] == {**original, "HF_HUB_DISABLE_XET": "1",
                             "HF_HUB_DISABLE_SHARED_BLOBS": "1",
                             "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"}


def test_missing_or_expired_download_does_not_commit(tmp_path):
    config, pins, directory = fake_cache(tmp_path)
    (directory / "tokenizer.json").unlink()
    commits = []
    with pytest.raises(ValueError, match="tokenizer"):
        runtime.prepare_cache(config, pins, EXPIRY, cache_root=tmp_path, runner=lambda *_a, **_k: None,
                              commit=lambda: commits.append(True), now=lambda: NOW)
    assert commits == []
    with pytest.raises(ValueError, match="expired"):
        runtime.prepare_cache(config, pins, EXPIRY, cache_root=tmp_path,
                              runner=lambda *_a, **_k: pytest.fail("download ran"), now=lambda: NOW + 3600)


def test_download_timeout_keeps_cache_uncommitted_and_uses_remaining_session(tmp_path):
    config, pins, _ = fake_cache(tmp_path)
    calls, commits = [], []

    def timed_out(command, **kwargs):
        calls.append(kwargs)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    with pytest.raises(subprocess.TimeoutExpired):
        runtime.prepare_cache(config, pins, EXPIRY, cache_root=tmp_path,
            runner=timed_out, commit=lambda: commits.append(True), now=lambda: NOW + 3500)
    assert len(calls) == 1 and calls[0]["timeout"] == 100
    assert calls[0]["env"]["HF_HUB_DISABLE_XET"] == "1"
    assert commits == []


@pytest.mark.parametrize("text", ["NVIDIA A100-SXM4-40GB, 40960, 580.95.05\n",
                                 "NVIDIA A100-SXM4-80GB, 81920, 570.95.05\n",
                                 "NVIDIA V100, 32768, 580.95.05\n", "broken\n",
                                 "NVIDIA A100, 81920, 580.95.05\n" * 2])
def test_unsuitable_gpu_or_driver_blocks_before_model_load(text):
    with pytest.raises(ValueError):
        runtime.check_gpu(runner=lambda *_a, **_k: types.SimpleNamespace(stdout=text))


def test_gpu_read_only_probe_has_timeout_and_matches_target():
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return types.SimpleNamespace(stdout="NVIDIA A100-SXM4-80GB, 81920, 580.95.05\n")

    result = runtime.check_gpu(runner=runner)
    assert result["memory_mib"] == 81920
    assert calls[0][0][0] == "nvidia-smi"
    assert calls[0][1]["timeout"] == 10
    assert calls[0][1]["shell"] is False


class Process:
    pid = 12345

    def __init__(self):
        self.done = False

    def poll(self):
        return 1 if self.done else None


class Thread:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def start(self):
        pass


def test_gpu_serve_is_offline_waits_for_health_and_never_places_secret_in_argv(tmp_path):
    config, pins, directory = fake_cache(tmp_path)
    calls, requests, threads = [], [], []
    process = Process()

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return process

    def thread(**kwargs):
        result = Thread(**kwargs)
        threads.append(result)
        return result

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): pass

    def open_health(request, **kwargs):
        requests.append((request, kwargs))
        return Response()

    result = runtime.start_server(config, pins, EXPIRY, cache_root=tmp_path,
        environment={"VLLM_API_KEY": KEY}, popen=popen, urlopen=open_health, now=lambda: NOW,
        monotonic=lambda: 0, thread_factory=thread, gpu_check=lambda: None)
    assert result is process
    command, kwargs = calls[0]
    assert KEY not in repr(command) and "--api-key" not in command
    assert "--trust-remote-code" not in command
    assert command[command.index("--model") + 1] == str(directory)
    assert command[command.index("--revision") + 1] == config["model_revision"]
    assert "--no-enable-log-requests" in command
    assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
    assert kwargs["env"]["TRANSFORMERS_OFFLINE"] == "1"
    assert kwargs["env"]["VLLM_API_KEY"] == KEY
    assert kwargs["start_new_session"] is True and kwargs["shell"] is False
    assert requests[0][0].full_url == "http://127.0.0.1:8000/health"
    assert requests[0][0].get_header("Authorization") == f"Bearer {KEY}"
    assert threads[0].kwargs["daemon"] is True
    assert threads[0].kwargs["args"][1] == NOW + 3600


def test_cache_or_expiry_failures_never_launch_gpu_process(tmp_path):
    config, pins, _ = fake_cache(tmp_path)
    for clock in (NOW, NOW + 3600):
        (tmp_path / "artha-evon-cache.json").unlink(missing_ok=True)
        with pytest.raises(ValueError):
            runtime.start_server(config, pins, EXPIRY, cache_root=tmp_path,
                environment={"VLLM_API_KEY": KEY}, now=lambda: clock,
                popen=lambda *_a, **_k: pytest.fail("GPU model launched"),
                urlopen=lambda *_a, **_k: pytest.fail("health called"))


def test_gpu_admission_failure_does_not_launch_model_or_call_health(tmp_path):
    config, pins, _ = fake_cache(tmp_path)

    def incompatible(): raise ValueError("incompatible driver")

    with pytest.raises(ValueError, match="driver"):
        runtime.start_server(config, pins, EXPIRY, cache_root=tmp_path,
            environment={"VLLM_API_KEY": KEY}, now=lambda: NOW, gpu_check=incompatible,
            popen=lambda *_a, **_k: pytest.fail("model launched"),
            urlopen=lambda *_a, **_k: pytest.fail("health called"))


def test_readiness_timeout_stops_subprocess_and_cancels_watchdog(tmp_path):
    config, pins, _ = fake_cache(tmp_path)
    process, stopped, threads = Process(), [], []
    clock = [0]

    def thread(**kwargs):
        result = Thread(**kwargs)
        threads.append(result)
        return result

    def sleep(seconds): clock[0] += seconds
    def unhealthy(*_a, **_k): raise OSError("not ready")

    with pytest.raises(TimeoutError):
        runtime.start_server(config, pins, "2026-10-28T12:00:02Z", cache_root=tmp_path,
            environment={"VLLM_API_KEY": KEY}, now=lambda: NOW + clock[0], monotonic=lambda: clock[0],
            popen=lambda *_a, **_k: process, urlopen=unhealthy, sleep=sleep,
            thread_factory=thread, stopper=lambda p: stopped.append(p), gpu_check=lambda: None)
    assert stopped == [process]
    assert threads[0].kwargs["args"][2].is_set()


def test_deadline_watchdog_cannot_be_extended_by_wall_clock_rollback():
    clock = [0]
    stops = []

    class Event:
        def is_set(self): return False
        def wait(self, seconds): clock[0] += seconds

    runtime.deadline_watchdog(Process(), NOW + 2, Event(), now=lambda: NOW - clock[0],
        monotonic=lambda: clock[0], stop=lambda p: stops.append(p.pid))
    assert clock[0] == 2 and stops == [12345]


def test_dead_parent_still_cleans_up_its_worker_group():
    stopped = []
    process = Process()
    process.done = True

    class Event:
        def is_set(self): return False

    runtime.deadline_watchdog(process, NOW + 5, Event(), now=lambda: NOW,
        monotonic=lambda: 0, stop=lambda p: stopped.append(p.pid))
    assert stopped == [12345]


def test_process_group_cleanup_escalates_if_workers_do_not_exit():
    signals = []

    class HungProcess:
        pid = 12345
        calls = 0
        def wait(self, timeout):
            self.calls += 1
            if self.calls == 1: raise subprocess.TimeoutExpired("vllm", timeout)

    runtime.stop_process(HungProcess(), kill_group=lambda pid, sig: signals.append((pid, sig)))
    assert signals == [(12345, signal.SIGTERM), (12345, runtime.KILL_SIGNAL)]


def test_lazy_modal_declaration_requires_proxy_auth_and_never_downloads_or_reads_env_files(monkeypatch):
    calls, definitions = [], []

    class Image:
        @classmethod
        def from_registry(cls, reference, **kwargs):
            calls.append(("image", reference, kwargs)); return cls()
        def entrypoint(self, value): calls.append(("entrypoint", value)); return self
        def add_local_file(self, local_path, remote_path, **kwargs):
            calls.append(("mount", Path(local_path).name, remote_path, kwargs)); return self

    class Volume:
        @classmethod
        def from_name(cls, name, **kwargs): calls.append(("volume", name, kwargs)); return cls()
        def with_mount_options(self, **kwargs): calls.append(("read_only", kwargs)); return self

    class Secret:
        @classmethod
        def from_name(cls, name, **kwargs): calls.append(("secret", name, kwargs)); return cls()

    class App:
        def __init__(self, name, **kwargs): calls.append(("app", name, kwargs))
        def function(self, **kwargs):
            def decorate(function): definitions.append((function.__name__, kwargs)); return function
            return decorate

    def web_server(**kwargs):
        calls.append(("web_server", kwargs))
        return lambda function: function

    def forbidden(*_a, **_k): raise AssertionError("Local declaration performed cloud/process work")

    fake_modal = types.SimpleNamespace(App=App, Image=Image, Volume=Volume, Secret=Secret, web_server=web_server)
    monkeypatch.setitem(sys.modules, "modal", fake_modal)
    monkeypatch.setattr(sys, "version_info", (3, 12, 11))
    monkeypatch.setenv("MODAL_EVON_SESSION_EXPIRES_AT", (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat())
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    definition = importlib.util.spec_from_file_location("artha_modal_declaration_test", ROOT / "scripts" / "modal_evon.py")
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    assert [name for name, _ in definitions] == ["download_weights", "serve"]
    cpu, gpu = [kwargs for _, kwargs in definitions]
    assert "gpu" not in cpu and cpu["timeout"] == 1800
    assert cpu["scaledown_window"] == 30
    assert gpu["gpu"] == "A100-80GB" and gpu["memory"] == (65536, 65536)
    assert gpu["min_containers"] == gpu["buffer_containers"] == 0
    assert "retries" not in gpu  # Modal Web Functions reject retry configuration.
    assert gpu["max_containers"] == 1 and gpu["scaledown_window"] == 300
    assert gpu["env"]["MODAL_EVON_SESSION_EXPIRES_AT"] == cpu["env"]["MODAL_EVON_SESSION_EXPIRES_AT"]
    assert gpu["env"]["HF_HUB_OFFLINE"] == "1"
    assert gpu["include_source"] is False and gpu["serialized"] is True
    assert gpu["region"] == "ap" and gpu["routing_region"] == "ap-south"
    assert ("web_server", {"port": 8000, "startup_timeout": 900, "requires_proxy_auth": True}) in calls
    assert ("entrypoint", []) in calls
    setup = next(call[2]["setup_dockerfile_commands"] for call in calls if call[0] == "image")
    assert setup == ["RUN ln -s /usr/bin/python3 /usr/local/bin/python",
                     "RUN python --version && python -m pip --version"]
    assert [call[1] for call in calls if call[0] == "mount"] == [
        "modal_evon_runtime.py", "inputs.verified-2026-10-28.json", "pins.verified-2026-10-28.json"]
