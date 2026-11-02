"""Public-corpus preparation tests use fabricated PCM and fake HTTP, not speech."""
import builtins
from contextlib import contextmanager
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import socket
import struct
import tarfile
import wave

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("public_human_preparation", ROOT / "scripts/prepare_public_human_speech.py")
public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public)


def wav_bytes(*, samples=128000, code=3, channels=1, rate=16000, bits=32, value=.125, payload=None):
    align = bits // 8 * channels
    fmt = struct.pack("<HHIIHH", code, channels, rate, rate * align, align, bits)
    if payload is None:
        if bits == 32:
            payload = np.full(samples * channels, value, dtype="<f4").tobytes()
        elif bits == 16:
            payload = struct.pack("<h", int(value * 32768)) * samples * channels
        else:
            payload = b"\x00" * samples * align
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks


def metadata_bytes(rows):
    return "".join(f"{sentence}\t{name}\tNative draft\tnormalized\tphonemes\t{samples}\tFEMALE\n" for sentence, name, samples in rows).encode("utf-8")


class FakeResponse:
    def __init__(self, content):
        self.content, self.read_bytes, self.closed = content, 0, False

    def raise_for_status(self):
        return None

    def iter_raw(self, chunk_size=16384):
        for start in range(0, len(self.content), chunk_size):
            chunk = self.content[start:start + chunk_size]
            self.read_bytes += len(chunk)
            yield chunk


class FakeClient:
    def __init__(self, content):
        self.content, self.calls, self.responses = content, [], []

    @contextmanager
    def stream(self, method, url):
        assert method == "GET"
        assert url.startswith(f"https://huggingface.co/datasets/{public.DATASET}/resolve/{public.REVISION}/data/")
        self.calls.append(url)
        response = FakeResponse(self.content[url.rsplit("/data/", 1)[1]])
        self.responses.append(response)
        try:
            yield response
        finally:
            response.closed = True


def archive_bytes(members):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, raw, kind in members:
            entry = tarfile.TarInfo(name)
            entry.type = kind
            if kind == tarfile.SYMTYPE:
                entry.linkname = "../private.wav"
            else:
                entry.size = len(raw)
            archive.addfile(entry, io.BytesIO(raw) if entry.isfile() else None)
    return output.getvalue()


def fake_corpus(per_language=10, *, unsafe=False):
    content = {}
    for language_index, language in enumerate(public.LANGUAGES):
        rows, members = [], []
        if unsafe:
            for name, kind in (("../900.wav", tarfile.REGTYPE), ("/901.wav", tarfile.REGTYPE), ("902.wav", tarfile.SYMTYPE)):
                rows.append((name, Path(name).name, 128000))
                members.append((name, wav_bytes(value=.7), kind))
        for index in range(per_language):
            name = f"{language_index * 100 + index + 1}.wav"
            rows.append((str(index + 1), name, 128000))
            members.append((f"test/{name}", wav_bytes(value=(language_index * 10 + index + 1) / 1000), tarfile.REGTYPE))
        # Deterministic incompressible tail establishes that stopping after the
        # requested clips closes the stream before downloading a whole archive.
        members.append(("irrelevant.bin", random.Random(100 + language_index).randbytes(100000), tarfile.REGTYPE))
        content[f"{language}_in/test.tsv"] = metadata_bytes(rows)
        content[f"{language}_in/audio/test.tar.gz"] = archive_bytes(members)
    return FakeClient(content)


def test_default_plan_loads_no_network_model_or_provider(monkeypatch, capsys):
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in {"httpx", "numpy", "onnxruntime", "artha_mesh"}:
            pytest.fail("Plan must not load a network or inference dependency")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: pytest.fail("Plan must not access network"))
    monkeypatch.setattr(public, "collect", lambda *_a, **_k: pytest.fail("Plan must not collect"))
    assert public.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["plan_only"] is True and report["maximum_recordings"] == 50
    assert report["provider_calls"] == report["inference_calls"] == 0
    assert report["independent_speaker_count"] is None
    assert report["individual_consent_reverified"] is report["voice_cloning"] is False


def test_metadata_preserves_exact_source_id_filename_sample_count():
    raw = metadata_bytes([("sentence-001", "123456.wav", 128000), ("sentence-002", "987654.wav", 320000)])
    assert public.parse_metadata(raw) == {
        "123456.wav": {"sentence_id": "sentence-001", "num_samples": 128000},
        "987654.wav": {"sentence_id": "sentence-002", "num_samples": 320000},
    }


def test_transcription_quotes_are_literal_tabs_do_not_join_adjacent_fields():
    raw = b'001\t123.wav\t"quoted raw text\tnormalized text"\tphonemes\t128000\tFEMALE\n'
    assert public.parse_metadata(raw) == {"123.wav": {"sentence_id": "001", "num_samples": 128000}}


@pytest.mark.parametrize("raw", [
    b"", b"a\tb\tc\n", b"\xff",
    metadata_bytes([("a", "../123.wav", 128000)]),
    metadata_bytes([("a", "name.wav", 128000)]),
    metadata_bytes([("a", "1.wav", 0)]),
    metadata_bytes([("a", "1.wav", -1)]),
    metadata_bytes([("a", "1.wav", "not-an-int")]),
    metadata_bytes([("a", "1.wav", 128000), ("b", "1.wav", 128000)]),
], ids=["empty", "field-count", "encoding", "traversal", "filename", "zero", "negative", "noninteger", "duplicate"])
def test_metadata_rejects_invalid_schema_counts_paths_encoding_and_duplicates(raw):
    with pytest.raises((ValueError, UnicodeDecodeError)):
        public.parse_metadata(raw)


def test_metadata_byte_bound_checked_before_parsing(monkeypatch):
    monkeypatch.setattr(public, "MAX_METADATA_BYTES", 3)
    with pytest.raises(ValueError, match="bound"):
        public.parse_metadata(b"1234")


@pytest.mark.parametrize("samples", [128000, 320000])
def test_native_float_quantization_preserves_count_source_bytes_and_pcm_hash(samples):
    values = np.resize(np.array([-1, -.5, 0, .25, .5, 1], dtype="<f4"), samples)
    raw = wav_bytes(samples=samples, payload=values.tobytes())
    original_hash = hashlib.sha256(raw).hexdigest()
    normalized = public.normalize_wav(raw, samples)
    with wave.open(io.BytesIO(normalized), "rb") as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getnframes()) == (16000, 1, 2, samples)
        pcm = audio.readframes(samples)
    expected = np.resize(np.array([-32768, -16384, 0, 8192, 16384, 32767], dtype="<i2"), samples).tobytes()
    assert pcm == expected and hashlib.sha256(pcm).digest() == hashlib.sha256(expected).digest()
    assert hashlib.sha256(raw).hexdigest() == original_hash
    assert public.normalize_wav(raw, samples) == normalized


def test_pcm16_source_payload_is_preserved_without_resampling():
    raw = wav_bytes(code=1, bits=16, value=.25)
    normalized = public.normalize_wav(raw, 128000)
    with wave.open(io.BytesIO(normalized), "rb") as audio:
        assert audio.getnframes() == 128000
        assert audio.readframes(128000) == struct.pack("<h", 8192) * 128000


def test_float_riff_accepts_native_fmt18_and_fact_metadata_chunks():
    raw = wav_bytes()
    fmt18 = raw[20:36] + b"\x00\x00"
    chunks = b"fmt " + struct.pack("<I", 18) + fmt18
    chunks += b"fact" + struct.pack("<II", 4, 128000)
    chunks += raw[36:]
    with_metadata = b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks
    assert public.normalize_wav(with_metadata, 128000) == public.normalize_wav(raw, 128000)


@pytest.mark.parametrize("raw,samples", [
    (b"not a WAV", 128000),
    (wav_bytes()[:-1], 128000),
    (wav_bytes(rate=48000), 128000),
    (wav_bytes(channels=2), 128000),
    (wav_bytes(code=6), 128000),
    (wav_bytes(bits=24), 128000),
    (wav_bytes(), 128001),
    (wav_bytes(samples=127999), 127999),
    (wav_bytes(samples=320001), 320001),
    (wav_bytes(value=float("nan")), 128000),
    (wav_bytes(value=float("inf")), 128000),
    (wav_bytes(value=1.1), 128000),
], ids=["not-riff", "truncated", "resample-forbidden", "stereo", "encoding", "bits", "count-mismatch", "too-short", "too-long", "nan", "infinite", "overrange"])
def test_normalization_rejects_invalid_truncated_unsupported_or_nonfinite_sources(raw, samples):
    with pytest.raises(ValueError):
        public.normalize_wav(raw, samples)


def test_normalization_rejects_corrupt_chunk_length_duplicate_data_and_rate_fields():
    raw = wav_bytes()
    oversized_chunk = raw[:40] + struct.pack("<I", len(raw)) + raw[44:]
    duplicate_chunk = raw + b"data" + struct.pack("<I", 0)
    duplicate_chunk = duplicate_chunk[:4] + struct.pack("<I", len(duplicate_chunk) - 8) + duplicate_chunk[8:]
    invalid_rate = raw[:28] + struct.pack("<I", 1234) + raw[32:]
    for malformed in (oversized_chunk, duplicate_chunk, invalid_rate):
        with pytest.raises(ValueError):
            public.normalize_wav(malformed, 128000)


def test_bounded_stream_retains_chunks_counts_bytes_and_supports_zero_read():
    response, budget = FakeResponse(b"abcdefghij"), {"download_bytes": 7}
    stream = public.BoundedStream(response, budget, 20)
    assert stream.read(0) == b"" and response.read_bytes == 0
    assert stream.read(3) == b"abc"
    assert stream.read(4) == b"defg"
    assert stream.read(20) == b"hij"
    assert stream.read(1) == b""
    assert stream.local_bytes == 10 and budget["download_bytes"] == 17


@pytest.mark.parametrize("limit,total", [(3, 100), (100, 3)])
def test_bounded_stream_refuses_local_or_global_budget(monkeypatch, limit, total):
    monkeypatch.setattr(public, "MAX_TOTAL_BYTES", total)
    budget = {"download_bytes": 0}
    stream = public.BoundedStream(FakeResponse(b"1234"), budget, limit)
    with pytest.raises(ValueError, match="budget"):
        stream.read(4)


@pytest.mark.parametrize("size", [-1, public.MAX_MEMBER_BYTES + 1])
def test_unbounded_or_oversized_stream_read_is_refused(size):
    with pytest.raises(ValueError, match="Unbounded"):
        public.BoundedStream(FakeResponse(b"unused"), {"download_bytes": 0}, 100).read(size)


def test_collects_ten_per_language_without_extracting_unsafe_members_or_whole_archives(tmp_path, monkeypatch):
    monkeypatch.setattr(public, "ROOT", tmp_path)
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: pytest.fail("Mock collector accessed real network"))
    monkeypatch.setattr(tarfile.TarFile, "extractall", lambda *_a, **_k: pytest.fail("Never extract archives"))
    monkeypatch.setattr(tarfile.TarFile, "extract", lambda *_a, **_k: pytest.fail("Never extract archive paths"))
    client = fake_corpus(unsafe=True)
    output = tmp_path / "work" / "public-human"
    report = public.collect(output, client=client)
    assert report["status"] == "complete" and report["source_recordings"] == 50
    assert report["languages_collected"] == dict.fromkeys(public.LANGUAGES, 10)
    assert report["provider_calls"] == report["inference_calls"] == 0
    assert len(client.calls) == report["public_file_requests"] == 10
    assert all(response.closed for response in client.responses)
    assert all(response.read_bytes < len(response.content) for response in client.responses[1::2])
    manifest = [json.loads(line) for line in (output / "manifest.public-human.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(manifest) == 50 and len(list((output / "recordings").glob("*.wav"))) == 50
    assert all(row["speaker_id"] is None and row["usage_permission"] == "public_license" for row in manifest)
    assert all(row["label"] == "genuine" and row["split"] == "evaluation" for row in manifest)
    for row in manifest:
        source = output / "originals" / (row["id"] + ".wav")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == row["source_sha256"]
        assert hashlib.sha256(Path(row["wav"]).read_bytes()).hexdigest() == row["sha256"]
    assert not (tmp_path / "900.wav").exists()
    assert (output / "ATTRIBUTION.txt").is_file()


def test_existing_outside_and_parent_traversal_destinations_are_refused_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(public, "ROOT", tmp_path)
    existing = tmp_path / "work" / "keep"
    existing.mkdir(parents=True)
    marker = existing / "original.wav"
    marker.write_bytes(b"keep original")
    for path in (existing, tmp_path / "outside", tmp_path / "work", Path("work/../outside")):
        with pytest.raises(ValueError):
            public.collect(path, client=FakeClient({}))
    assert marker.read_bytes() == b"keep original"


@pytest.mark.parametrize("count", [0, 11, -1, True, 1.5])
def test_invalid_collection_counts_fail_before_directory_or_network(tmp_path, monkeypatch, count):
    monkeypatch.setattr(public, "ROOT", tmp_path)
    output = tmp_path / "work" / "no-create"
    with pytest.raises(ValueError):
        public.collect(output, per_language=count, client=FakeClient({}))
    assert not output.exists()


def test_failed_collection_preserves_partial_files_and_safe_error_without_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(public, "ROOT", tmp_path)
    client = fake_corpus(per_language=1)
    client.content["ta_in/test.tsv"] = b"invalid private provider-like message"
    output = tmp_path / "work" / "partial"
    report = public.collect(output, per_language=1, client=client)
    assert report["status"] == "partial" and report["source_recordings"] == 1
    assert len(client.calls) == 3 and report["public_file_requests"] == 3
    assert "private provider-like" not in json.dumps(report)
    assert len(list((output / "originals").glob("*.wav"))) == 1
    assert (output / "manifest.public-human.jsonl").is_file()
    assert all(response.closed for response in client.responses)
