from __future__ import annotations

import io
import json
import math
import wave

import numpy as np
import pytest

from charcha.services.audio_screening import (
    MAX_SECONDS, SAMPLE_RATE, WINDOW_SAMPLES, LocalAudioScreener, read_pcm_wav,
)


def pcm_tone(samples=WINDOW_SAMPLES, hz=220, gain=.2):
    signal = gain * np.sin(2 * np.pi * hz * np.arange(samples) / SAMPLE_RATE)
    return (signal * 32767).astype("<i2").tobytes()


@pytest.fixture
def screener(tmp_path):
    return LocalAudioScreener(tmp_path / "missing.onnx")


class ModelDouble:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.inputs = []

    def run(self, names, inputs):
        self.inputs.append(inputs["wav"])
        result = next(self.outputs)
        if isinstance(result, Exception):
            raise result
        return [np.asarray([result])]


def with_model(screener, outputs):
    screener._session = ModelDouble(outputs)
    screener._model.update(kind="onnx_classifier", ready=True)
    return screener


@pytest.mark.parametrize("pcm,rate", [(b"", 16000), (b"x", 16000), (b"xx", 8000), (None, 16000)])
def test_rejects_malformed_pcm(screener, pcm, rate):
    with pytest.raises(ValueError):
        screener.analyze(pcm, rate)


def test_rejects_oversized_pcm_before_inference(screener):
    with pytest.raises(ValueError, match="30 seconds"):
        screener.analyze(bytes(MAX_SECONDS * SAMPLE_RATE * 2 + 2))


def test_dsp_never_certifies_human_or_synthetic(screener):
    result = screener.analyze(pcm_tone())
    assert result.verdict == "unknown"
    assert result.score is None
    assert result.analyzed_ms == 0
    assert "model_not_installed" in result.reasons
    assert result.diagnostics["pitch_hz"] == pytest.approx(220, rel=.03)
    assert result.diagnostics["jitter_percent"] < 1
    assert result.diagnostics["shimmer_percent"] < 1
    assert result.diagnostics["variation_method"].endswith("not_cycle_measurement")
    json.dumps(result.as_dict(), allow_nan=False)


def test_silence_is_unknown_not_live(screener):
    result = with_model(screener, []).analyze(bytes(WINDOW_SAMPLES * 2))
    assert result.verdict == "unknown"
    assert "insufficient_signal" in result.reasons
    assert result.score is None
    assert result.diagnostics["pitch_hz"] is None
    assert result.diagnostics["jitter_percent"] is None
    assert result.diagnostics["shimmer_percent"] is None
    assert screener._session.inputs == []


def test_short_audio_is_not_repeated_to_invent_observation(screener):
    result = with_model(screener, []).analyze(pcm_tone(6400))
    assert result.verdict == "unknown"
    assert result.audio_window_ms == 400
    assert result.windows_analyzed == 0
    assert "insufficient_audio_need_4040ms" in result.reasons


def test_clipping_prevents_classifier_claim(screener):
    audio = np.tile(np.array([-32768, 32767], dtype="<i2"), WINDOW_SAMPLES // 2)
    result = with_model(screener, []).analyze(audio.tobytes())
    assert result.verdict == "unknown"
    assert "severe_clipping" in result.reasons


@pytest.mark.parametrize("logits,verdict", [([4, -4], "suspicious"), ([-4, 4], "allow"), ([0, 0], "unknown")])
def test_upstream_spoof_class_zero_and_uncertainty_band(screener, logits, verdict):
    result = with_model(screener, [logits]).analyze(pcm_tone())
    assert result.verdict == verdict
    assert result.score == pytest.approx(1 / (1 + math.exp(logits[1] - logits[0])), abs=1e-6)
    assert result.audio_window_ms == 4037.5  # 64,600 / 16,000, not rounded 4.04 s
    assert result.analyzed_ms == 4037.5
    assert result.windows_analyzed == 1
    assert result.score_calibrated is False
    assert screener._session.inputs[0].shape == (1, WINDOW_SAMPLES)
    assert screener._session.inputs[0].dtype == np.float32


def test_multiple_windows_any_suspicious_and_bounded_tail(screener):
    result = with_model(screener, [[-4, 4], [4, -4]]).analyze(pcm_tone(WINDOW_SAMPLES * 2 + 320))
    assert result.verdict == "suspicious"
    assert result.windows_analyzed == 2
    assert result.partial_window_ms == 20
    assert "partial_tail_not_classified" in result.reasons


def test_partial_coverage_never_allows_entire_recording(screener):
    result = with_model(screener, [[-4, 4]]).analyze(pcm_tone(WINDOW_SAMPLES + 320))
    assert result.verdict == "unknown"
    assert result.score is not None
    assert result.windows_analyzed == 1


@pytest.mark.parametrize("output", [RuntimeError("private path or secret"), [float("nan"), 0], [0, 1, 2]])
def test_model_failure_and_invalid_scores_abstain_without_leaking(screener, output):
    result = with_model(screener, [output]).analyze(pcm_tone())
    assert result.verdict == "unknown"
    assert result.score is None
    assert "model_inference_failed" in result.reasons
    assert "private" not in json.dumps(result.as_dict())


def test_untrusted_artifact_not_loaded(tmp_path):
    artifact = tmp_path / "model.onnx"
    artifact.write_bytes(b"not an approved model")
    screener = LocalAudioScreener(artifact)
    assert not screener.status()["ready"]
    assert screener.status()["reason"] == "model_checksum_mismatch"


def test_thresholds_must_be_finite_ordered_probabilities(tmp_path):
    for low, high in [(1, 1), (.9, .1), (-.1, .8), (.2, float("nan"))]:
        with pytest.raises(ValueError):
            LocalAudioScreener(tmp_path / "missing", allow_threshold=low, threshold=high)


def make_wav(pcm, channels=1, rate=16000, width=2):
    target = io.BytesIO()
    with wave.open(target, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(pcm)
    return target.getvalue()


def test_wav_decoder_retains_samples():
    audio = pcm_tone()
    assert read_pcm_wav(make_wav(audio)) == (audio, 16000)


@pytest.mark.parametrize("raw", [b"not audio", b"", make_wav(b"xx", channels=2), make_wav(b"xx", rate=48000), make_wav(b"xx", width=1), make_wav(b"xxxx")[:-1]])
def test_wav_decoder_rejects_invalid_or_unsupported(raw):
    with pytest.raises(ValueError):
        read_pcm_wav(raw)
