from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.config import settings
from app.security import InvalidTokenError, NotAdminError, authenticate, authenticate_admin, decode_access_token
from tests.conftest import make_access_token


def test_authenticate_accepts_valid_token():
    token = make_access_token(user_id="abc-123")
    assert authenticate(f"Bearer {token}") == ("abc-123", None)


def test_authenticate_returns_admin_role_for_admin_token():
    token = make_access_token(user_id="admin-1", role="admin", admin_role="SUPERADMIN")
    assert authenticate(f"Bearer {token}") == ("admin-1", "SUPERADMIN")


def test_authenticate_defaults_admin_role_when_claim_missing():
    token = make_access_token(user_id="admin-1", role="admin")
    assert authenticate(f"Bearer {token}") == ("admin-1", "ADMIN")


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


def test_authenticate_admin_accepts_token_with_admin_role():
    token = make_access_token(user_id="admin-1", role="admin")
    assert authenticate_admin(f"Bearer {token}") == ("admin-1", None)


def test_authenticate_admin_returns_admin_role_claim():
    token = make_access_token(user_id="admin-1", role="admin", admin_role="SUPERADMIN")
    assert authenticate_admin(f"Bearer {token}") == ("admin-1", "SUPERADMIN")


def test_authenticate_admin_rejects_token_without_admin_role():
    token = make_access_token(user_id="abc-123")
    with pytest.raises(NotAdminError):
        authenticate_admin(f"Bearer {token}")


def test_authenticate_admin_rejects_token_with_other_role():
    token = make_access_token(user_id="abc-123", role="driver")
    with pytest.raises(NotAdminError):
        authenticate_admin(f"Bearer {token}")


def test_authenticate_admin_rejects_missing_header():
    with pytest.raises(InvalidTokenError):
        authenticate_admin(None)
