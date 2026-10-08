import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

from app import live
from tests.conftest import make_access_token

USER = "22222222-2222-2222-2222-222222222222"
OTHER = "33333333-3333-3333-3333-333333333333"


def test_valid_token_connects_and_answers_pings(client):
    with client.websocket_connect(f"/notifications/live?token={make_access_token(user_id=USER)}") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


@pytest.mark.parametrize(
    "token",
    ["", "garbage", make_access_token(user_id=USER, type="refresh")],
)
def test_bad_token_is_closed_as_unauthorized(client, token):
    with client.websocket_connect(f"/notifications/live?token={token}") as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == live.CLOSE_UNAUTHORIZED


def test_hint_reaches_only_that_users_sockets(client):
    mine = client.websocket_connect(f"/notifications/live?token={make_access_token(user_id=USER)}")
    theirs = client.websocket_connect(f"/notifications/live?token={make_access_token(user_id=OTHER)}")
    with mine as my_ws, theirs as their_ws:
        assert my_ws.receive_json() == {"type": "ready"}
        assert their_ws.receive_json() == {"type": "ready"}

        client.portal.call(live.hub.notify, [USER])

        assert my_ws.receive_json() == {"type": "notifications.changed"}
        # The other user got nothing: their next message is the pong to this ping.
        their_ws.send_text("ping")
        assert their_ws.receive_text() == "pong"


def test_closed_socket_leaves_the_hub(client):
    with client.websocket_connect(f"/notifications/live?token={make_access_token(user_id=USER)}") as ws:
        assert ws.receive_json() == {"type": "ready"}
        assert live.hub.connection_count() == 1
    # The server notices the close on its next receive.
    for _ in range(50):
        if live.hub.connection_count() == 0:
            break
        client.portal.call(asyncio.sleep, 0.01)
    assert live.hub.connection_count() == 0


def test_inbox_routes_are_proxied_with_the_user(client):
    token = make_access_token(user_id=USER)
    for method, path in [
        ("GET", "/notifications"),
        ("GET", "/notifications/unread-count"),
        ("POST", "/notifications/read"),
    ]:
        response = client.request(method, path, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        forwarded = client._mock_calls[-1]
        assert forwarded.url.host == "notifications-service.test"
        assert forwarded.url.path == path
        assert forwarded.headers["x-user-id"] == USER


def test_inbox_routes_require_a_token(client):
    assert client.get("/notifications").status_code == 401
    assert client._mock_calls == []


def test_uvicorn_log_lines_never_show_the_token():
    import logging

    from app.logger import RedactQueryTokenFilter

    record = logging.LogRecord(
        "uvicorn.error", logging.INFO, __file__, 1,
        '%s - "WebSocket %s" [accepted]', ("1.2.3.4:5", "/notifications/live?token=eyJabc.def&x=1"), None,
    )
    RedactQueryTokenFilter().filter(record)

    line = record.getMessage()
    assert "eyJabc" not in line
    assert "/notifications/live?token=***REDACTED***&x=1" in line
