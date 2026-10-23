import pytest
from conftest import auth, create_member, make_wav
from fastapi import HTTPException

from artha_mesh.services.voice import MAX_REFERENCE_BYTES, validate_reference


def test_reference_accepts_valid_duration_without_claiming_speech_detection():
    # Synthetic tone is deliberately not speech: validation only verifies format/energy.
    assert validate_reference(make_wav(), "audio/wav") == pytest.approx(5.1)


@pytest.mark.parametrize("clip,mime,status", [
    (b"not a wav", "audio/wav", 422),
    (make_wav(seconds=4.9), "audio/wav", 422),
    (make_wav(seconds=30.1), "audio/wav", 422),
    (make_wav(silent=True), "audio/wav", 422),
    (make_wav(width=1), "audio/wav", 422),
    (make_wav(), "audio/mpeg", 415),
    (b"0" * (MAX_REFERENCE_BYTES + 1), "audio/wav", 413),
], ids=["invalid-wav", "too-short", "too-long", "silence", "8-bit", "wrong-mime", "too-large"])
def test_reference_rejects_bad_format_duration_silence_and_size(clip, mime, status):
    with pytest.raises(HTTPException) as error:
        validate_reference(clip, mime)
    assert error.value.status_code == status


def upload(client, member, *, consent="true"):
    return client.post("/api/voice-profiles", data={
        "name": "My consenting voice", "consent": consent, "owner_token": member["session_token"],
    }, files={"audio_file": ("reference.wav", make_wav(), "audio/wav")})


def test_voice_enrollment_requires_explicit_consent(client):
    _, member = create_member(client)
    response = upload(client, member, consent="false")
    assert response.status_code == 422
    assert not client.app.state.store.voices


def test_profile_owner_only_cannot_leak_embedding_and_leave_discards_it(client):
    code, owner = create_member(client)
    _, other = create_member(client, code, name="Meena", language="ta")
    response = upload(client, owner)
    assert response.status_code == 201, response.text
    profile = response.json()
    assert profile["mode"] == "demo"
    assert "embedding" not in response.text
    cloned = {"voice_mode": "cloned", "voice_profile_id": profile["id"]}
    assert client.patch(f"/api/rooms/{code}/participants/me", headers=auth(other), json=cloned).status_code == 403
    assert client.delete(f"/api/voice-profiles/{profile['id']}", headers=auth(other)).status_code == 403
    assert client.patch(f"/api/rooms/{code}/participants/me", headers=auth(owner), json=cloned).status_code == 200
    client.post(f"/api/rooms/{code}/leave", headers=auth(owner), json={"participant_id": owner["participant"]["id"]})
    assert profile["id"] not in client.app.state.store.voices


def test_deleting_active_profile_returns_speaker_to_stock_voice(client):
    code, owner = create_member(client)
    profile = upload(client, owner).json()
    client.patch(f"/api/rooms/{code}/participants/me", headers=auth(owner), json={"voice_mode": "cloned", "voice_profile_id": profile["id"]})
    assert client.delete(f"/api/voice-profiles/{profile['id']}", headers=auth(owner)).status_code == 200
    participant = client.get(f"/api/rooms/{code}").json()["participants"][0]
    assert participant["voice_mode"] == "standard"
    assert profile["id"] not in client.app.state.store.voices
