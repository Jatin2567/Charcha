import array
import io
import math
import sys
import wave

import pytest
from fastapi.testclient import TestClient

from charcha.config import Settings


@pytest.fixture(autouse=True)
def isolated_usage_storage(monkeypatch, tmp_path, request):
    # Protocol fixtures act as a signed-in host. Identity tests use real cookies.
    from charcha.store import account_session
    marker = account_session.set(None if request.node.path.name.startswith("test_accounts") else "fixture")
    if not request.node.path.name.startswith("test_accounts"):
        from charcha.accounts import Account, Accounts
        monkeypatch.setenv("CHARCHA_PUBLIC_ORIGIN", "http://127.0.0.1:5180")
        monkeypatch.setenv("CHARCHA_MEETING_HOST_EMAIL", "host@example.test")
        monkeypatch.setattr(Accounts, "current", lambda self, req:
            Account("fixture", "host", "host@example.test", False, 4102444800))
    # Protocol fixtures must never spend or overwrite the operator's real ledger.
    monkeypatch.setenv("USAGE_DB_PATH", str(tmp_path / "usage.sqlite3"))
    # Legacy adapter fixtures use deterministic doubles, not operator-approved paid flows.
    # Approval enforcement is tested explicitly with usage_require_flow_approval=True.
    monkeypatch.setenv("USAGE_REQUIRE_FLOW_APPROVAL", "false")
    monkeypatch.setenv("GNANI_API_KEY", "")
    monkeypatch.setenv("EVON_API_KEY", "")
    yield
    account_session.reset(marker)


@pytest.fixture
def client():
    from charcha.main import create_app

    app = create_app(Settings(mode="demo", _env_file=None))
    with TestClient(app) as test_client:
        yield test_client


def make_wav(seconds=5.1, *, silent=False, rate=8000, width=2, channels=1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as clip:
        clip.setnchannels(channels)
        clip.setsampwidth(width)
        clip.setframerate(rate)
        if width == 2:
            values = array.array("h", (
                0 if silent else int(5000 * math.sin(2 * math.pi * 220 * index / rate))
                for index in range(int(seconds * rate) * channels)
            ))
            if sys.byteorder != "little":
                values.byteswap()
            clip.writeframes(values.tobytes())
        else:
            clip.writeframes(b"\x80" * int(seconds * rate) * channels * width)
    return buffer.getvalue()


def create_member(client, code=None, *, name="Asha", language="hi"):
    if code is None:
        response = client.post("/api/rooms", json={"title": "Test purchasing call"})
        assert response.status_code == 201, response.text
        code = response.json()["code"]
    response = client.post(f"/api/rooms/{code}/join", json={
        "name": name, "language": language, "voice_mode": "standard", "consent": False,
    })
    assert response.status_code == 200, response.text
    return code, response.json()


def auth(member):
    return {"Authorization": "Bearer " + member["session_token"]}
