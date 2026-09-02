import os

os.environ["JWT_SECRET"] = "test-secret"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["AUTH_SERVICE_URL"] = "http://auth-service.test"
os.environ["PARKING_SERVICE_URL"] = "http://parking-service.test"
os.environ["PAYMENT_SERVICE_URL"] = "http://payment-service.test"
os.environ["NOTIFICATIONS_SERVICE_URL"] = "http://notifications-service.test"
os.environ["BOOKING_SERVICE_URL"] = ""  # left unconfigured on purpose
os.environ["RABBITMQ_URL"] = "amqp://guest:guest@127.0.0.1:1/"  # unreachable on purpose

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings
from main import app


def make_access_token(user_id: str = "11111111-1111-1111-1111-111111111111", **overrides) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    payload.update(overrides)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


@pytest.fixture
def mock_upstream():
    """Records every request the gateway forwards and lets a test script a
    canned upstream response, without needing real services running."""
    calls = []
    script = {"status_code": 200, "json": {"ok": True}}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(script["status_code"], json=script["json"])

    return calls, script, handler


@pytest.fixture
def client(mock_upstream, monkeypatch):
    calls, script, handler = mock_upstream

    def override_state():
        app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with TestClient(app) as test_client:
        # Swap in the mocked transport after the real lifespan startup ran,
        # so we never hit the network for downstream calls in tests.
        override_state()
        test_client._mock_calls = calls
        test_client._mock_script = script
        yield test_client
