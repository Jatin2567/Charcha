from datetime import timedelta

from ..config import Settings


def agent_identity(room_id: str) -> str:
    return f"artha-agent-{room_id}"


def room_token(settings: Settings, code: str, identity: str, name: str, agent=False) -> str:
    from livekit import api

    grants = api.VideoGrants(
        room_join=True, room=code, can_publish=True, can_subscribe=True,
        can_publish_data=False, can_update_own_metadata=False,
        can_publish_sources=None if agent else ["microphone"],
    )
    token = (
        api.AccessToken(settings.livekit_api_key.get_secret_value(), settings.livekit_api_secret.get_secret_value())
        .with_identity(identity).with_name(name).with_grants(grants)
        .with_ttl(timedelta(seconds=settings.session_ttl_seconds))
    )
    if agent:
        token.with_kind("agent")
    return token.to_jwt()
