"""Download a bounded, licensed FLEURS human-speech sample; default is a plan.

No inference API, account token, provider environment, model load or cloning.
Original float WAVs and metadata remain local; analysis copies are PCM16 WAVs.
Archives are streamed, never extracted, and closed once the target is collected.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import struct
import tarfile
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
DATASET = "google/fleurs"
REVISION = "70bb2e84b976b7e960aa89f1c648e09c59f894dd"
LANGUAGES = ("hi", "ta", "bn", "te", "mr")
LICENSE = "cc-by-4.0"
ATTRIBUTION = "Google FLEURS — Conneau et al. (2022), FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech"
MIB = 1024 * 1024
MAX_TOTAL_BYTES = 100 * MIB
MAX_ARCHIVE_BYTES = 16 * MIB
MAX_METADATA_BYTES = 2 * MIB
MAX_MEMBER_BYTES = 2 * MIB
MAX_SCANNED_BYTES = 64 * MIB
MAX_RECORDINGS_PER_LANGUAGE = 10
FILENAME = re.compile(r"[0-9]{1,24}\.wav\Z")


def plan() -> dict:
    return {"schema_version": 1, "record_type": "public_human_speech_preparation", "plan_only": True,
            "source_dataset": DATASET, "source_revision": REVISION, "license": LICENSE,
            "attribution": ATTRIBUTION, "languages": list(LANGUAGES), "source_split": "test",
            "target_per_language": 10, "maximum_recordings": 50,
            "maximum_download_bytes": MAX_TOTAL_BYTES,
            "maximum_archive_bytes_per_language": MAX_ARCHIVE_BYTES,
            "usage_permission": "public_license", "individual_consent_reverified": False,
            "independent_speaker_count": None, "synthetic_recordings": 0,
            "provider_calls": 0, "inference_calls": 0, "voice_cloning": False,
            "note": "Publisher-described human read speech. Test-only convenience sample, not an independent-speaker benchmark or a detector accuracy result. No API/model requests; an explicit download only retrieves public files."}


def destination(path: Path) -> Path:
    work = ROOT / "work"
    candidate = path if path.is_absolute() else ROOT / path
    if ".." in path.parts or not candidate.is_relative_to(work) or candidate == work:
        raise ValueError("Use a new directory inside work/")
    for parent in (candidate, *candidate.parents):
        if parent.is_relative_to(work) and (parent.is_symlink() or bool(getattr(parent, "is_junction", lambda: False)())):
            raise ValueError("Linked output paths are not supported")
    if not candidate.resolve().is_relative_to(work.resolve()) or candidate.exists():
        raise ValueError("Output already exists or escapes work/")
    return candidate


def parse_metadata(raw: bytes) -> dict[str, dict]:
    if len(raw) > MAX_METADATA_BYTES:
        raise ValueError("Metadata exceeds the bound")
    result = {}
    # FLEURS is literal tab-delimited text; quotation marks belong to the
    # transcription and do not start CSV quoted fields.
    for row in csv.reader(io.StringIO(raw.decode("utf-8")), delimiter="\t", quoting=csv.QUOTE_NONE):
        if len(row) != 7 or not FILENAME.fullmatch(row[1]) or row[1] in result:
            raise ValueError("Unexpected FLEURS metadata")
        samples = int(row[5])
        if samples <= 0:
            raise ValueError("Invalid sample count")
        result[row[1]] = {"sentence_id": row[0], "num_samples": samples}
    if not result:
        raise ValueError("Empty source metadata")
    return result


def normalize_wav(raw: bytes, expected_samples: int) -> bytes:
    """Validate native mono16k WAV and quantize float32 to PCM16, without resampling."""
    import numpy as np
    if len(raw) > MAX_MEMBER_BYTES or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("Invalid or oversized source WAV")
    if struct.unpack_from("<I", raw, 4)[0] + 8 != len(raw):
        raise ValueError("Truncated source RIFF")
    fmt, payload, pos = None, None, 12
    while pos + 8 <= len(raw):
        kind, size = struct.unpack_from("<4sI", raw, pos)
        pos += 8
        if pos + size > len(raw):
            raise ValueError("Truncated WAV chunk")
        if kind == b"fmt ":
            if fmt is not None or size < 16:
                raise ValueError("Invalid WAV format chunk")
            fmt = struct.unpack_from("<HHIIHH", raw, pos)
        elif kind == b"data":
            if payload is not None:
                raise ValueError("Multiple data chunks")
            payload = raw[pos:pos + size]
        pos += size + size % 2
    if fmt is None or payload is None:
        raise ValueError("Missing WAV format/data")
    code, channels, rate, byte_rate, align, bits = fmt
    if channels != 1 or rate != 16000 or (code, bits) not in {(3, 32), (1, 16)}:
        raise ValueError("Only native mono16k float32 or PCM16 supported")
    if align != bits // 8 or byte_rate != rate * align or len(payload) != expected_samples * align:
        raise ValueError("Audio length/format differs from source metadata")
    if not 128000 <= expected_samples <= 320000:
        raise ValueError("Use natural 8–20 second recordings")
    if code == 3:
        values = np.frombuffer(payload, dtype="<f4")
        if not np.isfinite(values).all() or np.max(np.abs(values)) > 1.0001:
            raise ValueError("Invalid floating-point samples")
        payload = np.clip(np.rint(values.astype(np.float64) * 32768), -32768, 32767).astype("<i2").tobytes()
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(payload)
    return output.getvalue()


class BoundedStream:
    def __init__(self, response, budget: dict, local_limit: int):
        self.iterator = response.iter_raw(chunk_size=16384)
        self.buffer = bytearray()
        self.local_bytes = 0
        self.budget, self.local_limit = budget, local_limit

    def read(self, size: int) -> bytes:
        if not 0 <= size <= MAX_MEMBER_BYTES:
            raise ValueError("Unbounded stream read refused")
        while len(self.buffer) < size:
            try:
                chunk = next(self.iterator)
            except StopIteration:
                break
            self.local_bytes += len(chunk)
            self.budget["download_bytes"] += len(chunk)
            if self.local_bytes > self.local_limit or self.budget["download_bytes"] > MAX_TOTAL_BYTES:
                raise ValueError("Public download byte budget reached")
            self.buffer.extend(chunk)
        value = bytes(self.buffer[:size])
        del self.buffer[:size]
        return value


def _public_file(client, url: str, budget: dict, limit: int) -> bytes:
    with client.stream("GET", url) as response:
        response.raise_for_status()
        stream = BoundedStream(response, budget, limit)
        result = bytearray()
        while chunk := stream.read(16384):
            result.extend(chunk)
        return bytes(result)


def collect(output: Path, *, per_language: int = 10, client=None) -> dict:
    if type(per_language) is not int or not 1 <= per_language <= MAX_RECORDINGS_PER_LANGUAGE:
        raise ValueError("Collect 1–10 sources per language")
    output = destination(output)
    output.mkdir(parents=True)
    for folder in ("originals", "recordings", "metadata"):
        (output / folder).mkdir()
    owned_client = client is None
    if owned_client:
        import httpx
        client = httpx.Client(timeout=30, trust_env=False, follow_redirects=True, headers={"Accept-Encoding": "identity"})
    budget = {"download_bytes": 0}
    report = {**plan(), "plan_only": False, "status": "partial", "target_per_language": per_language,
              "languages_collected": {}, "public_file_requests": 0, "conversion": "native mono16k IEEEfloat32 quantized to PCM16; no resampling, gain, denoising, trimming or synthesis"}
    manifest, fingerprints = [], set()
    started = time.monotonic()
    try:
        for language in LANGUAGES:
            config = language + "_in"
            base = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/data/{config}"
            report["public_file_requests"] += 1
            metadata_raw = _public_file(client, base + "/test.tsv", budget, MAX_METADATA_BYTES)
            metadata = parse_metadata(metadata_raw)
            (output / "metadata" / f"{language}-test.tsv").write_bytes(metadata_raw)
            selected, sentence_ids, scanned = 0, set(), 0
            report["public_file_requests"] += 1
            with client.stream("GET", base + "/audio/test.tar.gz") as response:
                response.raise_for_status()
                stream = BoundedStream(response, budget, MAX_ARCHIVE_BYTES)
                with tarfile.open(fileobj=stream, mode="r|gz") as archive:
                    for index, member in enumerate(archive):
                        scanned += member.size
                        if index >= 500 or scanned > MAX_SCANNED_BYTES or time.monotonic() - started > 240:
                            raise ValueError("Public archive scan budget reached")
                        path = PurePosixPath(member.name)
                        name = path.name
                        if (not member.isfile() or ".." in path.parts or path.is_absolute()
                                or not FILENAME.fullmatch(name) or name not in metadata):
                            continue
                        entry = metadata[name]
                        if (not 128000 <= entry["num_samples"] <= 320000 or member.size > MAX_MEMBER_BYTES
                                or entry["sentence_id"] in sentence_ids):
                            continue
                        source = archive.extractfile(member)
                        if source is None:
                            raise ValueError("Missing archive source")
                        raw = source.read(MAX_MEMBER_BYTES + 1)
                        normalized = normalize_wav(raw, entry["num_samples"])
                        digest = hashlib.sha256(normalized).hexdigest()
                        if digest in fingerprints:
                            continue
                        selected += 1
                        identifier = f"public-fleurs-{language}-{selected:03d}"
                        original = output / "originals" / f"{identifier}.wav"
                        wav = output / "recordings" / f"{identifier}.wav"
                        original.write_bytes(raw)
                        wav.write_bytes(normalized)
                        manifest.append({"schema_version": 1, "id": identifier, "wav": str(wav),
                                         "language": language, "label": "genuine", "split": "evaluation",
                                         "source_dataset": DATASET, "source_revision": REVISION,
                                         "source_config": config, "source_split": "test", "source_filename": name,
                                         "num_samples": entry["num_samples"], "sha256": digest,
                                         "source_sha256": hashlib.sha256(raw).hexdigest(),
                                         "usage_permission": "public_license", "license": LICENSE,
                                         "attribution": ATTRIBUTION, "speaker_id": None})
                        sentence_ids.add(entry["sentence_id"])
                        fingerprints.add(digest)
                        if selected == per_language:
                            break
            report["languages_collected"][language] = selected
            print(json.dumps({"language": language, "human_recordings": selected, "public_download_bytes_so_far": budget["download_bytes"], "provider_calls": 0}), flush=True)
            if selected != per_language:
                raise ValueError("Insufficient compatible source recordings")
        report["status"] = "complete"
    except Exception:
        report["error"] = "public_source_collection_incomplete; partial originals preserved; no automatic retry"
    finally:
        if owned_client:
            client.close()
        report.update(source_recordings=len(manifest), download_bytes=budget["download_bytes"], wall_seconds=round(time.monotonic() - started, 3))
        with (output / "manifest.public-human.jsonl").open("x", encoding="utf-8") as target:
            target.write("".join(json.dumps(row, ensure_ascii=True) + "\n" for row in manifest))
        (output / "collection-report.json").write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        (output / "ATTRIBUTION.txt").write_text(ATTRIBUTION + "\nhttps://huggingface.co/datasets/google/fleurs\nhttps://creativecommons.org/licenses/by/4.0/\nRevision: " + REVISION + "\nHuman-read provenance and permission rely on the public publisher release, not personally collected consent. Independent speakers unknown. Analysis copies quantized to PCM16; originals preserved. Local evaluation only, no training or voice cloning.\n", encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--per-language", type=int, default=10)
    args = parser.parse_args(argv)
    if args.download and not args.output_dir or args.output_dir and not args.download:
        parser.error("Downloading requires --download and a new --output-dir")
    try:
        report = collect(args.output_dir, per_language=args.per_language) if args.download else plan()
    except (ValueError, OSError):
        print("Use a new output directory inside work/ and 1–10 sources per language; existing data is preserved.")
        return 2
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report.get("status", "complete") == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
