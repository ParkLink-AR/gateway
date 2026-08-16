from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.config import settings
from app.security import InvalidTokenError, authenticate, decode_access_token
from tests.conftest import make_access_token


def test_authenticate_accepts_valid_token():
    token = make_access_token(user_id="abc-123")
    assert authenticate(f"Bearer {token}") == "abc-123"


def test_authenticate_rejects_missing_header():
    with pytest.raises(InvalidTokenError):
        authenticate(None)


def test_authenticate_rejects_non_bearer_header():
    with pytest.raises(InvalidTokenError):
        authenticate("Basic abc123")


def test_authenticate_rejects_expired_token():
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {"sub": "abc-123", "type": "access", "iat": now - timedelta(hours=1), "exp": now - timedelta(minutes=1)},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(expired)


def test_authenticate_rejects_wrong_signature():
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": "abc-123", "type": "access", "iat": now, "exp": now + timedelta(minutes=15)},
        "a-different-secret",
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_authenticate_rejects_non_access_token():
    now = datetime.now(timezone.utc)
    refresh_like = jwt.encode(
        {"sub": "abc-123", "type": "refresh", "iat": now, "exp": now + timedelta(minutes=15)},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(refresh_like)
