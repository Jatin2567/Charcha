import pytest
from starlette.websockets import WebSocketDisconnect

from conftest import create_member


def test_browser_upgrade_authenticates_without_a_token_in_url(client):
    code, member = create_member(client)
    protocols = ["artha-events", "artha-token." + member["session_token"]]
    with client.websocket_connect(
        f"/api/rooms/{code}/events", subprotocols=protocols,
        headers={"origin": "http://localhost:5173"},
    ) as socket:
        assert socket.accepted_subprotocol == "artha-events"
        assert socket.receive_json()["type"] == "room.snapshot"


def test_upgrade_header_does_not_grant_access_to_another_room(client):
    _, member = create_member(client)
    other_code, _ = create_member(client)
    with pytest.raises(WebSocketDisconnect) as failure:
        with client.websocket_connect(
            f"/api/rooms/{other_code}/events",
            subprotocols=["artha-events", "artha-token." + member["session_token"]],
            headers={"origin": "http://localhost:5173"},
        ):
            pass
    assert failure.value.code == 1008
