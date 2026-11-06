"""Operate a single approved five-language batch. Default prints the plan offline.

--rehearse exercises the RTC and ledger paths with doubles in a temporary folder.
--execute requires the plan hash, the one-use stage folder and a bounded Modal session.
"""
import argparse
import asyncio
from contextlib import contextmanager, ExitStack
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import wave

from five_language_call import ROOT, conference_turn
import check_hindi_tamil_e2e as shared
from check_modal_readiness import load_credentials
from charcha.config import Settings
from charcha.providers.evon import EvonTranslator
from charcha.providers.gnani import GnaniSpeech
from charcha.services.usage import UsageGuard

STAGE = json.loads((ROOT / "web/src/data/fiveLanguageStage.json").read_text())
OUT = ROOT / "work" / STAGE["id"]
HOST = "https://jatin2567--artha-evon-test-serve.ap-south.modal.run"
ORIGIN = "ws://127.0.0.1:17880"
FLEURS = ROOT / "work/public-human-fleurs-20261029-v2"
CLIPS = {
    "hi": ("001", "effc3fddae7c20d647d42463efdea8a5646d031804d2888ad0710422341afd2e"),
    "ta": ("004", "065e84eba27181eded566de7a7cca18ce9b659a3664cd6c166fa30772547cde5"),
    "bn": ("002", "94e54cfd17915a6d6f508af56ff909fdb00611f89514174316ecf859576f8f75"),
    "te": ("007", "2237523e6bd5b4147433881456c2a41857b269b660f1b43294901a96024a6830"),
    "mr": ("003", "7b48a3138bd5557d7d79903c5ffbf37831002e19ebc423f886e1b6efdccc744e"),
}
LIMITS = dict(stt_connections=1, stt_seconds=25, mt_requests=1, mt_characters=500,
              tts_requests=1, tts_characters=300, voice_enrollments=0)


def plan(*, modal_overhead_usd=None, modal_workspace_ceiling_usd=None):
    from five_language_modal import load_allocation
    routes = STAGE["routes"]
    if (STAGE["flow_limit"] != 10 or STAGE["modal_usd_limit"] != 5 or STAGE["per_flow"] != LIMITS
            or len(routes) != 10 or len({frozenset(pair) for pair in routes}) != 10
            or any(len(pair) != 2 or pair[0] == pair[1] or not set(pair) <= CLIPS.keys() for pair in routes)):
        raise ValueError("Stage exceeds the reviewed limits")
    return {**STAGE, "endpoint": HOST, "model": shared.MODEL, "prompt_version": shared._prompt.PROMPT_VERSION,
            "inputs": CLIPS, "modal_session_seconds": 1500, "retries": 0, "source_tts": 0,
            "modal_allocation": load_allocation(), "modal_other_cost_allowance_usd": modal_overhead_usd,
            "modal_workspace_usage_ceiling_usd": modal_workspace_ceiling_usd}


def inputs():
    manifest = {r["id"]: r for r in map(json.loads, (FLEURS / "manifest.public-human.jsonl").read_text().splitlines())}
    data = {}
    for lang, (index, checksum) in CLIPS.items():
        clip = f"public-fleurs-{lang}-{index}"
        raw = (FLEURS / "recordings" / (clip + ".wav")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != checksum:
            raise ValueError("Unexpected source audio")
        with wave.open(io.BytesIO(raw)) as wav:
            if (wav.getframerate(), wav.getsampwidth(), wav.getnchannels()) != (16000, 2, 1):
                raise ValueError("Expected mono PCM16 at 16 kHz")
            pcm = wav.readframes(wav.getnframes())
        with (FLEURS / "metadata" / f"{lang}-test.tsv").open(encoding="utf8") as meta:
            reference = next(row[2] for row in csv.reader(meta, delimiter="\t")
                             if row[1] == manifest[clip]["source_filename"])
        data[lang] = (pcm, reference)
    return data


@contextmanager
def local_media(folder, base_port=17880):
    for port, kind in [(base_port, socket.SOCK_STREAM), (base_port + 1, socket.SOCK_STREAM), (base_port + 2, socket.SOCK_DGRAM)]:
        with socket.socket(type=kind) as sock:
            sock.bind(("127.0.0.1", port))
    config = f"rtc:\n  tcp_port: {base_port + 1}\n  enable_loopback_candidate: true\nlogging:\n  level: warn\n"
    binary = ROOT / ("work/bin/livekit-server.exe" if os.name == "nt" else "work/bin/livekit-server")
    with (folder / "rtc.log").open("xb") as log:
        proc = subprocess.Popen([str(binary), "--dev", "--bind", "127.0.0.1", "--port", str(base_port),
            "--udp-port", str(base_port + 2), "--config-body", config], stdout=log, stderr=log)
        try:
            for _ in range(80):
                if proc.poll() is not None:
                    raise RuntimeError("Local media exited")
                try:
                    with socket.create_connection(("127.0.0.1", base_port), .2):
                        break
                except OSError:
                    time.sleep(.1)
            else:
                raise TimeoutError("Local media did not start")
            yield
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def settings_for(folder, live):
    common = dict(mode="live", livekit_url=ORIGIN, livekit_internal_url=ORIGIN, livekit_api_key="devkey",
                  livekit_api_secret="secret", usage_require_flow_approval=True, gnani_stt_model="prisma-v3.0",
                  audio_screening_mode="off", usage_voice_enrollments_per_day=0, usage_stt_max_retries=0,
                  provider_timeout_seconds=25, timbre_model="timbre-v2.5")
    if not live:
        return Settings(_env_file=None, **common, gnani_api_key="fixture", evon_model="fixture",
                        evon_base_url="http://127.0.0.1:9/v1", usage_db_path=folder / "usage.sqlite")
    private = load_credentials(ROOT / "work/modal-private/client.json")
    cfg = Settings(**common, evon_base_url=HOST + "/v1", evon_model=shared.MODEL,
                   evon_api_key=private["api_key"], evon_modal_key=private["modal_key"],
                   evon_modal_secret=private["modal_secret"])
    if (cfg.missing_live_config() or cfg.gnani_tts_url != shared.OFFICIAL_TTS or cfg.gnani_stt_url != shared.OFFICIAL_STT):
        raise ValueError("Approved speech endpoints or credentials unavailable")
    return cfg


def save(folder, report):
    pending = folder / "report.tmp"
    content = json.dumps(report, indent=2, allow_nan=False)
    # A concurrent Windows reader can briefly deny an atomic replace. Retry
    # only this local journal write, never a socket, grant or inference call.
    for attempt in range(20):
        try:
            pending.write_text(content, encoding="utf8")
            pending.replace(folder / "report.json")
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.05)


async def calls(folder, live, settings, clips, report, deadline, max_cases=10):
    from verify_five_language_routing import Providers
    guard = UsageGuard(settings)
    speech = GnaniSpeech(settings, guard) if live else Providers()
    translator = EvonTranslator(settings, guard) if live else speech
    try:
        failures = 0
        for row in report["routes"][:max_cases]:
            if time.time() + 90 >= deadline or failures >= 2:
                break
            source, target = row["source"], row["target"]
            flow = guard.approve_flow(purpose="live_interpretation", seconds=90, budgets=LIMITS)
            try:
                row.update(status="attempted", stage="setup")
                save(folder, report)
                with guard.bind_flow(flow["id"]):
                    async with asyncio.timeout(78):
                        pcm, reference = clips[source]
                        texts, audio = await conference_turn(settings, guard, speech, translator, source, target, pcm, row)
                shared.save_wav(folder / f"{source}-{target}.wav", audio)
                shared.write_private(folder / f"{source}-{target}.json",
                    json.dumps({**texts, "reference":reference}, ensure_ascii=False).encode())
                row.update(status="receiver_decoded", stage="complete")
                failures = 0
            except Exception as exc:
                row.update(status="failed", error_kind=type(exc).__name__)
                failures += 1
            finally:
                closed = guard.close_flow(flow["id"])
                row.update(used=closed["used"], grant_closed=closed["status"] == "closed")
                save(folder, report)
            print(json.dumps(row), flush=True)
    finally:
        try:
            if live:
                await asyncio.gather(speech.aclose(), translator.aclose())
        finally:
            guard.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--rehearse", nargs="?", const="hi-ta",
                      choices=[f"{a}-{b}" for a in CLIPS for b in CLIPS if a != b])
    mode.add_argument("--execute", metavar="REVIEWED_PLAN_SHA256")
    parser.add_argument("--modal-overhead-usd", help="Reviewed allowance for build/CPU/storage/network")
    parser.add_argument("--modal-workspace-ceiling-usd", help="Reviewed gross workspace usage ceiling, at most $5")
    args = parser.parse_args()
    proposal = plan(modal_overhead_usd=args.modal_overhead_usd,
                    modal_workspace_ceiling_usd=args.modal_workspace_ceiling_usd)
    fingerprint = shared.digest(proposal)
    if not args.rehearse and args.execute is None:
        print(json.dumps({"plan": proposal, "sha256": fingerprint}, indent=2))
        return 0
    if args.execute is not None and args.execute != fingerprint:
        raise ValueError("The reviewed plan hash is required")
    live = args.execute is not None
    if live:
        from five_language_modal import amount
        amount(args.modal_overhead_usd, "reviewed other-cost allowance", allow_zero=True)
        if amount(args.modal_workspace_ceiling_usd, "reviewed workspace gross usage ceiling") > 5:
            raise ValueError("This runner cannot exceed the historical $5 stage limit")
    clips = inputs()
    with ExitStack() as stack:
        if live:
            folder = OUT
            folder.mkdir(exist_ok=False)  # Exclusive one-time stage admission, also across restarts.
        else:
            folder = Path(stack.enter_context(tempfile.TemporaryDirectory(dir=ROOT / "work")))
        routes = STAGE["routes"] if live else [args.rehearse.split("-")]
        report = {"stage_id": STAGE["id"], "plan_sha256": fingerprint, "real_providers": live,
                  "physical_devices": False, "meaning_review": "pending", "routes": [
                      {"source": a, "target": b, "status": "unattempted"} for a,b in routes]}
        save(folder, report)
        cfg = settings_for(folder, live)
        stack.enter_context(local_media(folder))
        deadline = time.time() + proposal["modal_session_seconds"]
        if live:
            from five_language_modal import bounded_session
            deadline = stack.enter_context(bounded_session(folder, HOST, deadline,
                overhead_usd=proposal["modal_other_cost_allowance_usd"],
                workspace_ceiling_usd=proposal["modal_workspace_usage_ceiling_usd"]))
        asyncio.run(calls(folder, live, cfg, clips, report, deadline, 10 if live else 1))
        return int(any(r["status"] != "receiver_decoded" for r in report["routes"][:10 if live else 1]))


if __name__ == "__main__":
    sys.exit(main())
