from __future__ import annotations

from jose import JWTError, jwt

from app.config import settings


class InvalidTokenError(Exception):
    """Raised when the Authorization header is missing, malformed, or the
    token is invalid/expired. Callers turn this into a 401."""


def extract_bearer_token(authorization_header: str | None) -> str:
    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise InvalidTokenError("Missing bearer token")
    token = authorization_header.removeprefix("Bearer ").strip()
    if not token:
        raise InvalidTokenError("Empty bearer token")
    return token


def decode_access_token(token: str) -> dict:
    """Verifies signature + expiry using the same secret/algorithm auth-service
    signs with. This is a fast edge check only: it doesn't know about session
    revocation, suspended/deleted users, etc. auth-service remains the source
    of truth for those and still re-validates on its own protected routes.
    """
    verification_key = settings.JWT_PUBLIC_KEY if settings.JWT_PUBLIC_KEY else settings.JWT_SECRET
    try:
        payload = jwt.decode(token, verification_key, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != "access":
        raise InvalidTokenError("Not an access token")
    if not payload.get("sub"):
        raise InvalidTokenError("Token missing subject")

    return payload


def authenticate(authorization_header: str | None) -> str:
    """Returns the authenticated user_id (token 'sub' claim), raising
    InvalidTokenError otherwise."""
    token = extract_bearer_token(authorization_header)
    payload = decode_access_token(token)
    return payload["sub"]
