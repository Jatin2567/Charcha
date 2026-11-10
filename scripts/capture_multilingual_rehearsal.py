"""Capture three independent accounts in the real local Charcha interface.

No provider access: authored text replaces inference, .env is never loaded,
Python rejects external networking and browser connections are confined by CSP.
This verifies workflow behaviour, not speech quality, RTC or provider latency.
Run after npm run build with the server virtual environment's Python.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))


def local_host(host):
    if host in (None, "localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def install_network_guard(blocked):
    def audit(event, args):
        host = None
        if event == "socket.connect":
            address = args[1]
            if isinstance(address, tuple):
                host = address[0]
            else:
                return  # Local UNIX-domain socket, where supported.
        elif event == "socket.getaddrinfo":
            host = args[0]
        else:
            return
        if not local_host(host):
            blocked.append(event)  # Do not record any credentials or URLs.
            raise RuntimeError("Offline rehearsal forbids external networking")
    sys.addaudithook(audit)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Browser:
    def __init__(self, connection):
        self.connection, self.serial = connection, 0

    async def call(self, method, params=None, tab=None):
        self.serial += 1
        message = {"id": self.serial, "method": method, "params": params or {}}
        if tab:
            message["sessionId"] = tab
        await self.connection.send(json.dumps(message))
        while True:
            result = json.loads(await asyncio.wait_for(self.connection.recv(), 20))
            if result.get("id") == self.serial:
                if "error" in result:
                    raise RuntimeError(result["error"])
                return result.get("result", {})

    async def js(self, tab, expression):
        result = await self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": True, "userGesture": True,
        }, tab)
        if result.get("exceptionDetails"):
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    async def until(self, tab, expression):
        for _ in range(100):
            if await self.js(tab, expression):
                return
            await asyncio.sleep(.1)
        # DOM contains only generated fixture identities/text, never real login data.
        body = await self.js(tab, "document.body.innerText")
        raise RuntimeError(f"UI condition failed: {expression}\n{body[:3500]}")

    async def api(self, tab, path, body=None, token=None):
        options = {"method": "POST" if body is not None else "GET",
                   "headers": {"Content-Type": "application/json", "X-Charcha-Request": "1"}}
        if token:
            options["headers"]["Authorization"] = "Bearer " + token
        if body is not None:
            options["body"] = json.dumps(body)
        return await self.js(tab, "(async()=>{const r=await fetch(" + json.dumps(path) + "," +
                             json.dumps(options) + ");if(!r.ok)throw Error(await r.text());return r.json()})()")

    async def click(self, tab, label):
        element = "Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===" + json.dumps(label) + ")"
        await self.until(tab, "!!(" + element + ")")
        await self.js(tab, element + ".click()")


async def run(args):
    import httpx
    import uvicorn
    import websockets
    from fastapi.staticfiles import StaticFiles
    from charcha.config import Settings

    out = (ROOT / args.output).resolve()
    if not out.is_relative_to((ROOT / "work").resolve()):
        raise ValueError("Capture output must stay inside this repository's work folder")
    out.mkdir(parents=True, exist_ok=True)
    fixture_path = ROOT / "evaluation/multilingual_rehearsal.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if fixture["kind"] != "authored_offline_fixture" or len(fixture["participants"]) != 3:
        raise ValueError("Expected the three-participant offline fixture")
    if not (ROOT / "dist/index.html").is_file():
        raise RuntimeError("Run npm run build first")

    blocked = []
    install_network_guard(blocked)
    # main.py has a global app. Isolate its settings BEFORE importing it too.
    Settings.model_config["env_file"] = None
    field_names = set()
    for name, field in Settings.model_fields.items():
        field_names.add(name.lower())
        alias = field.validation_alias
        field_names.update(str(a).lower() for a in getattr(alias, "choices", []))
        if isinstance(alias, str):
            field_names.add(alias.lower())
    for key in list(os.environ):
        if key.lower() in field_names:
            del os.environ[key]

    receipt = {"kind": "automated_offline_three_party_rehearsal", "status": "running",
               "provider_calls": 0, "physical_rtc_call": False, "test_accounts": 3,
               "translation_evidence": "authored fixture, not provider output",
               "human_translation_review": False, "provider_latency_measured": False,
               "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
               "checks": [], "screenshots": []}
    with tempfile.TemporaryDirectory(prefix="charcha-three-party-") as temporary:
        folder = Path(temporary)
        os.environ["USAGE_DB_PATH"] = str(folder / "global.sqlite")
        os.environ["CHARCHA_MODE"] = "demo"
        from charcha.main import create_app
        from charcha.accounts import Account, COOKIE
        from charcha.store import token_digest
        from charcha.services import pipeline as pipeline_module

        port, debugging = free_port(), free_port()
        origin = f"http://127.0.0.1:{port}"
        settings = Settings(_env_file=None, mode="demo", usage_db_path=folder / "usage.sqlite",
                            charcha_public_origin=origin, charcha_meeting_host_email="host@example.test",
                            gnani_api_key="", evon_api_key="", evon_base_url="", evon_serverless=False,
                            livekit_url="", livekit_internal_url="", livekit_api_key="", livekit_api_secret="",
                            voice_cloning_required=False, audio_screening_mode="off", audio_screening_on_demand=False)
        app = create_app(settings)
        original, corrected = fixture["turns"]
        pipeline_module.sample_for = lambda text, *_: {"fixture": True} if text == original["source"] else None

        async def replay(item):
            row = corrected if item.turn.replaces_id else original
            if item.turn.text != row["source"] or set(item.targets) != {"te", "pa"}:
                raise RuntimeError("Unexpected fixture input or language fan-out")
            item.turn.translations = row["translations"].copy()
            item.turn.status = "complete"
            item.state.broadcast("transcript.final", {"turn": item.turn.model_dump(mode="json")})

        app.state.pipeline._process = replay

        @app.middleware("http")
        async def restrict_browser(request, call_next):
            response = await call_next(request)
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' blob:; "
                "connect-src 'self' ws://127.0.0.1:*; frame-src 'none'; object-src 'none'"
            )
            return response

        app.mount("/", StaticFiles(directory=ROOT / "dist", html=True))
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False))
        thread = threading.Thread(target=server.run, daemon=True)
        chrome = None
        thread.start()
        try:
            executable = Path(os.environ["ProgramFiles"]) / "Google/Chrome/Application/chrome.exe"
            chrome = subprocess.Popen([
                str(executable), "--headless=new", "--disable-gpu", "--disable-background-networking",
                "--disable-extensions", "--no-first-run", "--no-default-browser-check",
                "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
                f"--user-data-dir={folder / 'chrome'}", f"--remote-debugging-port={debugging}", "about:blank",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            async with httpx.AsyncClient(trust_env=False) as client:
                for _ in range(150):
                    try:
                        ws = (await client.get(f"http://127.0.0.1:{debugging}/json/version")).json()["webSocketDebuggerUrl"]
                        if server.started:
                            break
                    except (httpx.HTTPError, KeyError):
                        pass
                    if chrome.poll() is not None:
                        raise RuntimeError("Isolated local Chrome exited before capture")
                    await asyncio.sleep(.1)
                else:
                    raise RuntimeError("Local capture startup timed out")
            async with websockets.connect(ws, origin=None, max_size=2**24) as connection:
                browser = Browser(connection)
                tabs, memberships = [], []
                for person in fixture["participants"]:
                    context = (await browser.call("Target.createBrowserContext"))["browserContextId"]
                    target = (await browser.call("Target.createTarget", {"url": "about:blank", "browserContextId": context}))["targetId"]
                    tab = (await browser.call("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]
                    tabs.append(tab)
                    await browser.call("Page.enable", {}, tab)
                    await browser.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False}, tab)
                    raw = secrets.token_urlsafe(32)
                    key = token_digest(raw)
                    app.state.accounts.sessions[key] = Account(key, person["subject"], person["subject"] + "@example.test", False, time.time() + 900)
                    await browser.call("Network.setCookie", {"name": COOKIE, "value": raw, "url": origin, "httpOnly": True}, tab)
                    await browser.call("Page.navigate", {"url": origin}, tab)
                    await browser.until(tab, "document.readyState==='complete' && location.origin!=='null'")

                host, telugu, punjabi = tabs
                room = await browser.api(host, "/api/rooms", {"title": fixture["title"]})
                code = room["code"]
                state = app.state.store.rooms[code]
                for guest in tabs[1:]:
                    requested = await browser.api(guest, f"/api/rooms/{code}/admission", {})
                    assert requested["status"] == "pending"
                pending = await browser.api(host, f"/api/rooms/{code}/admission/requests")
                assert len(pending["requests"]) == 2
                for entry in pending["requests"]:
                    approved = await browser.api(host, f"/api/rooms/{code}/admission/requests/{entry['id']}", {"decision": "approve"})
                    assert approved["status"] == "approved"
                receipt["checks"].append("two real admission requests approved by fixture host")
                for tab, person in zip(tabs, fixture["participants"]):
                    who = await browser.api(tab, "/api/account")
                    member = await browser.api(tab, f"/api/rooms/{code}/join", {"name": person["name"], "language": person["language"], "consent": True})
                    memberships.append(member)
                    preferences = {"name": person["name"], "language": person["language"], "autoCaptions": True, "micEnabled": False}
                    await browser.js(tab, "localStorage.setItem(" + json.dumps("charcha.preferences." + who["scope"]) + "," + json.dumps(json.dumps(preferences)) + ")")
                    await browser.js(tab, "sessionStorage.setItem(" + json.dumps("charcha.membership." + who["session_scope"]) + "," + json.dumps(json.dumps(member)) + ")")
                    await browser.call("Page.navigate", {"url": origin + "/#/room/" + code}, tab)
                    # Hash navigations can complete after the CDP command returns.
                    # Reload only after the requested route is actually active.
                    await browser.until(tab, "location.hash === " + json.dumps("#/room/" + code))
                    await browser.call("Page.reload", {}, tab)
                    await browser.until(tab, "!!document.querySelector('[aria-label=\"Leave conversation\"]')")

                async def shot(tab, name, expand=False):
                    await browser.js(tab, "document.querySelectorAll('.turn-understanding').forEach(x=>x.open=false)")
                    if expand:
                        await browser.js(tab, "document.querySelectorAll('.turn-understanding').forEach(x=>{if(!x.querySelector('summary')?.textContent.includes('Earlier'))x.open=true})")
                    await browser.js(tab, "(()=>{const feed=document.querySelector('.caption-lines');const last=feed?.querySelector('.caption-line:last-child');if(feed&&last)feed.scrollTop+=last.getBoundingClientRect().top-feed.getBoundingClientRect().top})()")
                    await asyncio.sleep(.5)
                    await browser.js(tab, "(()=>{let x=document.getElementById('capture-disclosure');if(!x){x=document.createElement('div');x.id='capture-disclosure';x.style='position:fixed;top:0;left:0;right:0;background:#16316f;color:#fff;padding:7px;text-align:center;font:600 13px system-ui;z-index:99999;pointer-events:none';document.body.appendChild(x)}x.textContent='AUTOMATED LOCAL REHEARSAL · scripted translations · no provider audio or latency claims'})()")
                    picture = await browser.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}, tab)
                    (out / (name + ".png")).write_bytes(base64.b64decode(picture["data"]))
                    receipt["screenshots"].append(name + ".png")

                async def see_translation(tab, language, row):
                    await browser.until(tab, "document.body.innerText.includes(" + json.dumps(row["translations"][language]) + ")")

                async def confirm(tab):
                    await browser.until(tab, "!!document.querySelector('[aria-label=\"Confirm understanding\"]')")
                    await browser.js(tab, "document.querySelector('[aria-label=\"Confirm understanding\"]').click()")
                    await browser.until(tab, "!!document.querySelector('[aria-label=\"You confirmed understanding\"]')")

                await shot(host, "01-three-participants")
                await browser.api(host, f"/api/rooms/{code}/text", {"text": original["source"]}, memberships[0]["session_token"])
                await see_translation(telugu, "te", original)
                await see_translation(punjabi, "pa", original)
                await shot(telugu, "02-telugu-original")
                await shot(punjabi, "03-punjabi-original")
                first = state.turns[0]
                listener_ids = {m["participant"]["id"] for m in memberships[1:]}
                assert set(first.listeners) == listener_ids
                await confirm(telugu)
                assert set(first.confirmed_by) == {memberships[1]["participant"]["id"]}
                await shot(host, "04-one-listener-pending", True)
                await confirm(punjabi)
                assert set(first.confirmed_by) == listener_ids
                receipt["checks"].append("two language branches with independent listener acknowledgements")

                await browser.click(host, "Correct for everyone")
                await browser.until(host, "!!document.querySelector('.correction-editor textarea')")
                await browser.js(host, "(()=>{let x=document.querySelector('.correction-editor textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(x," + json.dumps(corrected["source"]) + ");x.dispatchEvent(new Event('input',{bubbles:true}))})()")
                await shot(host, "05-correction-editor")
                await browser.click(host, "Share correction")
                await see_translation(telugu, "te", corrected)
                await see_translation(punjabi, "pa", corrected)
                second = state.turns[1]
                assert len(state.turns) == 2
                assert first.superseded_by == second.id and second.replaces_id == first.id
                assert not second.confirmed_by and set(second.listeners) == listener_ids
                assert set(first.confirmed_by) == listener_ids
                await shot(telugu, "06-telugu-correction-pending")
                await shot(punjabi, "07-punjabi-correction-pending")
                receipt["checks"].append("correction preserves earlier version and resets both confirmations")
                await confirm(telugu)
                await confirm(punjabi)
                assert set(second.confirmed_by) == listener_ids
                await browser.until(host, "document.body.innerText.includes('All listed listeners confirmed understanding')")
                await shot(host, "08-both-confirmed", True)

                await browser.call("Page.reload", {}, telugu)
                await see_translation(telugu, "te", corrected)
                await browser.until(telugu, "!!document.querySelector('[aria-label=\"You confirmed understanding\"]')")
                assert {p.id for p in state.room.participants} == {m["participant"]["id"] for m in memberships}
                account = await browser.api(telugu, "/api/account")
                retained = await browser.js(telugu, "JSON.parse(sessionStorage.getItem(" + json.dumps("charcha.membership." + account["session_scope"]) + "))?.participant.id")
                assert retained == memberships[1]["participant"]["id"]
                await shot(telugu, "09-refreshed", True)
                receipt["checks"].append("refresh retains the same fixture membership and corrected caption")

                await browser.js(telugu, "document.querySelector('[aria-label=\"Leave conversation\"]').click()")
                await browser.until(telugu, "!!document.querySelector('.modal-actions .danger')")
                await browser.js(telugu, "document.querySelector('.modal-actions .danger').click()")
                await browser.until(telugu, "location.hash.startsWith('#/recap/')")
                await browser.until(telugu, "document.body.innerText.includes(" + json.dumps(corrected["translations"]["te"]) + ")")
                await browser.click(telugu, "Save recap")
                await browser.until(telugu, "document.body.innerText.includes('Saved on this device')")
                await shot(telugu, "10-recap")
                await browser.click(telugu, "WhatsApp recap")
                await browser.until(telugu, "!!document.querySelector('.recap-share-preview')")
                await shot(telugu, "11-whatsapp")
                exported = await browser.js(telugu, "document.querySelector('.recap-share-preview').value")
                (out / "whatsapp.txt").write_text(exported, encoding="utf-8")
                assert corrected["source"] in exported and corrected["translations"]["te"] in exported
                await browser.call("Page.reload", {}, telugu)
                await browser.until(telugu, "document.body.innerText.includes('Saved on this device')")
                await browser.until(telugu, "document.body.innerText.includes(" + json.dumps(corrected["translations"]["te"]) + ")")
                receipt["checks"].append("bilingual saved recap and WhatsApp text contain corrected content")
                if args.gallery:
                    # Capture the current product without fabricating provider samples.
                    # The Telugu fixture account owns the recap saved above.
                    gallery = []
                    for route, label, tab in [
                        ("/", "home", host), ("/join/" + code, "join", host),
                        ("/performance", "performance", telugu),
                        ("/audio-lab", "audio-lab", host), ("/voices", "voices", host),
                        ("/tests", "tests", host), ("/history", "history", telugu),
                        ("/settings", "settings", host),
                    ]:
                        await browser.call("Page.navigate", {"url": origin + "/#" + route}, tab)
                        await asyncio.sleep(.8)
                        await shot(tab, "page-" + label)
                        gallery.append({"route": route, "file": "page-" + label + ".png",
                                        "kind": "offline_interface_capture"})
                    (out / "gallery.json").write_text(json.dumps(gallery, indent=2), encoding="utf-8")
                    receipt["checks"].append("current portal gallery captured without provider measurements")
                assert not state.performance_samples, "Fixture must not create provider performance samples"
                assert not blocked, "Unexpected external network attempt"
                receipt["checks"].append("zero external Python connections and zero invented provider timing samples")
                receipt["status"] = "passed"
        except BaseException:
            receipt["status"] = "failed"
            raise
        finally:
            if chrome is not None:
                chrome.terminate()
                try:
                    chrome.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    chrome.kill()
                    chrome.wait()
            server.should_exit = True
            await asyncio.to_thread(thread.join, 10)
            receipt["processes_stopped"] = (chrome is None or chrome.poll() is not None) and not thread.is_alive()
            if not receipt["processes_stopped"]:
                receipt["status"] = "failed"
            receipt["blocked_external_attempts"] = len(blocked)
            (out / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            if not receipt["processes_stopped"]:
                raise RuntimeError("The local capture did not shut down cleanly")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="work/demo-video/automated-three-party/captures")
    parser.add_argument("--gallery", action="store_true")
    print("Preparing the isolated offline three-participant capture.", flush=True)
    asyncio.run(run(parser.parse_args()))
