from types import SimpleNamespace

import pytest

from charcha.config import Settings
from charcha.services.audio_screening import LocalAudioScreener, WINDOW_SAMPLES
from charcha.services.screening_runtime import ScreeningRuntime


@pytest.mark.parametrize("threads", [0, 5, True, 1.5])
def test_invalid_cpu_budget_is_rejected_before_model_loading(threads, tmp_path):
    with pytest.raises(ValueError, match="CPU threads"):
        LocalAudioScreener(tmp_path / "missing.onnx", cpu_threads=threads)


def test_cpu_tuning_never_shortens_evidence_or_changes_thresholds(tmp_path):
    one = LocalAudioScreener(tmp_path / "missing.onnx")
    two = LocalAudioScreener(tmp_path / "missing.onnx", cpu_threads=2)
    assert one.status()["cpu_threads"] == 1
    assert two.status()["cpu_threads"] == 2
    assert one.window_samples == two.window_samples == WINDOW_SAMPLES == 64600
    assert one.threshold == two.threshold == .8
    assert one.allow_threshold == two.allow_threshold == .2
    # A faster CPU setting does not make a one-second input classifiable.
    assert two.analyze(b"\x01\x00" * 16000).verdict == "unknown"
    assert two.status()["score_calibrated"] is False


def test_runtime_passes_the_explicit_cpu_profile_without_running_inference(monkeypatch):
    import charcha.services.screening_runtime as module
    recorded = {}

    def capture(path, **options):
        recorded.update(options)
        return SimpleNamespace()

    monkeypatch.setattr(module, "LocalAudioScreener", capture)
    settings = Settings(_env_file=None, audio_screening_mode="monitor", audio_screening_cpu_threads=2)
    runtime = ScreeningRuntime(settings)
    assert recorded["cpu_threads"] == 2
    assert recorded["load_model"] is True
    assert runtime.mode == "monitor"
