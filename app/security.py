from __future__ import annotations

from jose import JWTError, jwt

from app.config import settings


class InvalidTokenError(Exception):
    """Raised when the Authorization header is missing, malformed, or the
    token is invalid/expired. Callers turn this into a 401."""


class NotAdminError(Exception):
    """Raised when the token is otherwise valid but its role claim isn't
    "admin". Callers turn this into a 403 -- the caller is authenticated,
    just not authorized for this route."""


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
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
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


def authenticate_admin(authorization_header: str | None) -> str:
    """Returns the authenticated admin's user_id (token 'sub' claim).

    Raises InvalidTokenError for a missing/malformed/expired token (401), or
    NotAdminError for an otherwise-valid token whose role claim isn't "admin"
    (403). auth-service doesn't issue role:"admin" tokens today (see
    payment-service's identical convention in src/security.js) -- they're
    minted by hand with the shared JWT_SECRET for ParkLink staff.
    """
    token = extract_bearer_token(authorization_header)
    payload = decode_access_token(token)
    if payload.get("role") != "admin":
        raise NotAdminError("Admin privileges required")
    return payload["sub"]
