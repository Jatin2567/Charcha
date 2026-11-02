"""Offline, experimental audio screening with explicit uncertainty.

DSP measurements are signal diagnostics, never evidence that a voice is human or
synthetic. Optional, checksum-pinned AASIST inference runs only on the CPU. Its
softmax is an uncalibrated model score, not a probability of fraud or accuracy.
No network access, remote code, pickle, audio persistence or provider calls.
"""
from __future__ import annotations

import hashlib
import io
import math
import time
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import numpy as np

MODEL_ID = "SpeechAntiSpoofingBenchmarks/AASIST"
MODEL_REVISION = "16774d458d86d2a021ae31646c1bf66a5331b53e"
MODEL_SHA256 = "130e536266b7c537f9a13029e1612a9f392fd1cc827783683b6d1c062a3db5e1"
DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "models" / "aasist" / "model.onnx"
SAMPLE_RATE = 16000
WINDOW_SAMPLES = 64600
MAX_SECONDS = 30


@dataclass(frozen=True)
class ScreenResult:
    verdict: Literal["allow", "suspicious", "unknown"]
    score: float | None
    model: dict
    compute_ms: float
    audio_window_ms: float
    analyzed_ms: float
    reasons: list[str]
    diagnostics: dict
    experimental: bool = True
    threshold: float | None = None
    allow_threshold: float | None = None
    windows_analyzed: int = 0
    partial_window_ms: float = 0
    score_calibrated: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def read_pcm_wav(raw: bytes) -> tuple[bytes, int]:
    """Decode only bounded, uncompressed 16-bit 16 kHz mono WAV uploads."""
    if not raw or len(raw) > MAX_SECONDS * SAMPLE_RATE * 2 + 65536:
        raise ValueError("Use a nonempty WAV file of at most 30 seconds")
    try:
        with wave.open(io.BytesIO(raw), "rb") as source:
            if (source.getcomptype() != "NONE" or source.getnchannels() != 1
                    or source.getsampwidth() != 2 or source.getframerate() != SAMPLE_RATE):
                raise ValueError("Use uncompressed 16-bit, 16 kHz, mono WAV audio")
            frames = source.getnframes()
            if not 0 < frames <= MAX_SECONDS * SAMPLE_RATE:
                raise ValueError("Use a WAV recording of at most 30 seconds")
            pcm = source.readframes(frames)
            if len(pcm) != frames * 2:
                raise ValueError("WAV audio is truncated")
            return pcm, SAMPLE_RATE
    except (wave.Error, EOFError) as exc:
        raise ValueError("The uploaded file is not a supported PCM WAV recording") from exc


def _diagnostics(audio: np.ndarray) -> dict:
    """Autocorrelation pitch and frame-period/amplitude variation proxies.

    Jitter/shimmer here compare consecutive voiced 40 ms frames, not clinical
    cycle-level measurements. They are deliberately not classifier inputs.
    """
    rms = float(np.sqrt(np.mean(audio * audio, dtype=np.float64)))
    periods: list[float] = []
    amplitudes: list[float] = []
    previous_frame: int | None = None
    period_changes: list[float] = []
    amplitude_changes: list[float] = []
    silence = 0
    frames = 0
    for frame_index, start in enumerate(range(0, len(audio) - 639, 320)):
        frame = audio[start:start + 640]
        energy = float(np.mean(frame * frame))
        frames += 1
        if energy < 1e-6:
            silence += 1
            previous_frame = None
            continue
        centered = frame - frame.mean()
        spectrum = np.fft.rfft(centered, 2048)
        correlation = np.fft.irfft(spectrum * spectrum.conjugate(), 2048)[:640]
        if correlation[0] <= 1e-10:
            previous_frame = None
            continue
        # 60–400 Hz. Require a local peak, avoiding a lag-boundary maximum.
        low, high = 40, 267
        candidates = np.flatnonzero(
            (correlation[low:high] >= correlation[low - 1:high - 1])
            & (correlation[low:high] > correlation[low + 1:high + 1])
        ) + low
        if not len(candidates):
            previous_frame = None
            continue
        lag = int(candidates[np.argmax(correlation[candidates])])
        if correlation[lag] / correlation[0] < .55:
            previous_frame = None
            continue
        amplitude = float(np.ptp(centered))
        if previous_frame == frame_index - 1 and periods and amplitudes:
            # Exclude octave jumps; real speech boundaries are not jitter.
            if .75 <= lag / periods[-1] <= 1.25:
                period_changes.append(abs(lag - periods[-1]))
                amplitude_changes.append(abs(amplitude - amplitudes[-1]))
        periods.append(float(lag))
        amplitudes.append(amplitude)
        previous_frame = frame_index
    return {
        "rms_dbfs": round(20 * math.log10(max(rms, 1e-8)), 3),
        "peak": round(float(np.max(np.abs(audio))), 6),
        "clipping_ratio": round(float(np.mean(np.abs(audio) >= 32760 / 32768)), 6),
        "silence_ratio": round(silence / frames, 6) if frames else float(rms < .001),
        "zero_crossing_rate": round(float(np.mean(np.signbit(audio[1:]) != np.signbit(audio[:-1]))), 6) if len(audio) > 1 else 0,
        "pitch_hz": round(SAMPLE_RATE / float(np.median(periods)), 3) if periods else None,
        "jitter_percent": round(100 * float(np.mean(period_changes)) / float(np.mean(periods)), 4) if len(period_changes) >= 2 else None,
        "shimmer_percent": round(100 * float(np.mean(amplitude_changes)) / max(float(np.mean(amplitudes)), 1e-8), 4) if len(amplitude_changes) >= 2 else None,
        "voiced_frames": len(periods),
        "variation_method": "consecutive_voiced_frame_proxy_not_cycle_measurement",
    }


class LocalAudioScreener:
    window_samples = WINDOW_SAMPLES
    window_ms = WINDOW_SAMPLES * 1000 / SAMPLE_RATE

    def __init__(self, model_path: str | Path | None = None, *, threshold: float = .8,
                 allow_threshold: float = .2, load_model: bool = True, cpu_threads: int = 1):
        if not (0 <= allow_threshold < threshold <= 1):
            raise ValueError("Screening thresholds must satisfy 0 <= allow < suspicious <= 1")
        if type(cpu_threads) is not int or not 1 <= cpu_threads <= 4:
            raise ValueError("Screening CPU threads must be an integer from 1 to 4")
        self.cpu_threads = cpu_threads
        self.threshold, self.allow_threshold = threshold, allow_threshold
        self._session = None
        self._load_reason = "model_not_installed"
        self._model = {"id": MODEL_ID, "kind": "signal_only", "revision": MODEL_REVISION,
                       "sha256": None, "ready": False, "license": "MIT",
                       "validated_on_indian_meeting_audio": False}
        if not load_model:
            self._load_reason = "screening_disabled"
            return
        path = Path(model_path) if model_path is not None else DEFAULT_MODEL
        if not path.is_file():
            return
        # Only this reviewed export is supported. No model-provided Python runs.
        try:
            if path.stat().st_size > 4_000_000:
                self._load_reason = "model_checksum_mismatch"
                return
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != MODEL_SHA256:
                self._load_reason = "model_checksum_mismatch"
                return
            self._model["sha256"] = digest
            import onnxruntime as ort

            options = ort.SessionOptions()
            options.intra_op_num_threads = cpu_threads
            options.inter_op_num_threads = 1
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            options.log_severity_level = 3
            options.add_session_config_entry("session.intra_op.allow_spinning", "0")
            session = ort.InferenceSession(str(path), sess_options=options,
                                           providers=["CPUExecutionProvider"])
            inputs, outputs = session.get_inputs(), session.get_outputs()
            if (len(inputs) != 1 or inputs[0].name != "wav"
                    or inputs[0].shape[-1] != WINDOW_SAMPLES
                    or inputs[0].type != "tensor(float)"
                    or len(outputs) != 1 or outputs[0].name != "logits"):
                raise ValueError("Unsupported AASIST ONNX contract")
            self._session = session
            self._model.update(kind="onnx_classifier", ready=True)
            self._load_reason = "experimental_model_not_locally_calibrated"
        except ImportError:
            self._load_reason = "onnxruntime_not_installed"
        except Exception:
            self._load_reason = "model_load_failed"

    def status(self) -> dict:
        return {**self._model, "reason": self._load_reason,
                "window_ms": self.window_ms, "threshold": self.threshold,
                "allow_threshold": self.allow_threshold, "score_calibrated": False,
                "cpu_threads": self.cpu_threads}

    def analyze(self, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> ScreenResult:
        if sample_rate != SAMPLE_RATE:
            raise ValueError("Screening requires 16 kHz mono PCM")
        if not isinstance(pcm, bytes) or not pcm or len(pcm) % 2:
            raise ValueError("Provide nonempty signed 16-bit little-endian PCM bytes")
        if len(pcm) > MAX_SECONDS * SAMPLE_RATE * 2:
            raise ValueError("Screening input is limited to 30 seconds")
        started = time.perf_counter()
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        diagnostic = _diagnostics(audio)
        reasons = ["experimental_not_authenticity_proof", "dsp_is_diagnostic_only"]
        scores: list[float] = []
        partial = len(audio) % WINDOW_SAMPLES
        verdict = "unknown"
        if len(audio) < WINDOW_SAMPLES:
            reasons.append("insufficient_audio_need_4040ms")
        elif diagnostic["rms_dbfs"] < -50 or diagnostic["silence_ratio"] > .9:
            reasons.append("insufficient_signal")
        elif diagnostic["clipping_ratio"] > .1:
            reasons.append("severe_clipping")
        elif self._session is None:
            reasons.append(self._load_reason)
        else:
            failed = False
            for start in range(0, len(audio) - WINDOW_SAMPLES + 1, WINDOW_SAMPLES):
                segment = audio[start:start + WINDOW_SAMPLES]
                # A silent window is not allowed to certify the surrounding clip.
                if float(np.mean(segment * segment)) < 1e-5:
                    reasons.append("unscored_silent_window")
                    failed = True
                    continue
                try:
                    logits = np.asarray(self._session.run(["logits"], {"wav": segment[None, :]})[0], dtype=np.float64)
                    if logits.shape != (1, 2) or not np.all(np.isfinite(logits)):
                        raise ValueError("Invalid classifier output")
                    logits -= logits.max(axis=1, keepdims=True)
                    exp = np.exp(logits)
                    scores.append(float(exp[0, 0] / exp.sum()))  # upstream class 0 = spoof
                except Exception:
                    failed = True
                    reasons.append("model_inference_failed")
                    break
            if scores:
                if max(scores) >= self.threshold:
                    verdict = "suspicious"
                    reasons.append("model_score_above_experimental_threshold")
                elif max(scores) <= self.allow_threshold and not failed and not partial:
                    verdict = "allow"
                    reasons.append("model_score_below_experimental_threshold")
                else:
                    reasons.append("uncertain_or_incomplete_coverage")
            if partial:
                reasons.append("partial_tail_not_classified")
        return ScreenResult(
            verdict=verdict, score=round(max(scores), 6) if scores else None,
            model=dict(self._model), compute_ms=round((time.perf_counter() - started) * 1000, 3),
            audio_window_ms=round(len(audio) * 1000 / SAMPLE_RATE, 3),
            analyzed_ms=round(len(scores) * self.window_ms, 3),
            reasons=list(dict.fromkeys(reasons)), diagnostics=diagnostic,
            threshold=self.threshold if self._session is not None else None,
            allow_threshold=self.allow_threshold if self._session is not None else None,
            windows_analyzed=len(scores), partial_window_ms=round(partial * 1000 / SAMPLE_RATE, 3),
        )
