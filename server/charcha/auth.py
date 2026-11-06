from fastapi import Header, HTTPException


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "A conversation membership token is required")
    token = authorization[7:].strip()
    if not token or len(token) > 256:
        raise HTTPException(401, "Invalid membership token")
    return token
