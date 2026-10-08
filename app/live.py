"""Live notification hints for the app while it's open.

The app keeps one WebSocket open to the gateway (/notifications/live). Whenever
notifications-service saves something new in a user's inbox it publishes
`notification.created` on the shared exchange; every gateway instance receives its own
copy (an exclusive, auto-deleted queue per instance) and tells that user's open sockets
"something changed", and the app refetches its inbox. The socket never carries the
notification itself -- the inbox stays the source of truth, so a missed hint only means
the app catches up the next time it refetches (on returning to the foreground, or its slow
fallback poll)."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict

import aio_pika
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from app.config import settings
from app.security import InvalidTokenError, decode_access_token

ROUTING_KEY = "notification.created"
RETRY_DELAY_SECONDS = 5
# Close code the app reads as "log in again / refresh the token, then reconnect".
CLOSE_UNAUTHORIZED = 4401


class LiveHub:
    """The open sockets of this gateway instance, by user id."""

    def __init__(self) -> None:
        self._sockets: dict[str, set[WebSocket]] = defaultdict(set)

    def add(self, user_id: str, socket: WebSocket) -> None:
        self._sockets[user_id].add(socket)

    def remove(self, user_id: str, socket: WebSocket) -> None:
        sockets = self._sockets.get(user_id)
        if not sockets:
            return
        sockets.discard(socket)
        if not sockets:
            del self._sockets[user_id]

    def connection_count(self) -> int:
        return sum(len(sockets) for sockets in self._sockets.values())

    async def notify(self, user_ids: list[str]) -> None:
        for user_id in user_ids:
            for socket in list(self._sockets.get(user_id, ())):
                try:
                    await socket.send_json({"type": "notifications.changed"})
                except Exception:  # noqa: BLE001 - a dead socket is just dropped
                    self.remove(user_id, socket)


hub = LiveHub()


async def live_endpoint(websocket: WebSocket) -> None:
    """WebSocket /notifications/live?token=<access token>. Browsers and React Native
    can't set an Authorization header on a WebSocket, hence the token in the query. The
    socket is accepted before it's checked so the app can read the close code."""
    await websocket.accept()
    try:
        payload = decode_access_token(websocket.query_params.get("token", ""))
    except InvalidTokenError:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return

    user_id = payload["sub"]
    hub.add(user_id, websocket)
    try:
        await websocket.send_json({"type": "ready"})
        while True:
            # The app pings now and then so idle proxies (Cloudflare drops a silent
            # socket after ~100s) keep the connection.
            if await websocket.receive_text() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove(user_id, websocket)


async def _relay(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    async with message.process(ignore_processed=True):
        try:
            user_ids = json.loads(message.body.decode("utf-8")).get("user_ids") or []
        except (ValueError, UnicodeDecodeError, AttributeError):
            return
        await hub.notify([str(user_id) for user_id in user_ids])


async def run_consumer(stop: asyncio.Event) -> None:
    """Relays notification.created to the open sockets, reconnecting to RabbitMQ for as
    long as the gateway runs -- RabbitMQ being down never takes the HTTP proxy with it."""
    while not stop.is_set():
        try:
            connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            async with connection:
                channel = await connection.channel()
                exchange = await channel.declare_exchange(
                    settings.EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
                )
                queue = await channel.declare_queue(exclusive=True, auto_delete=True)
                await queue.bind(exchange, routing_key=ROUTING_KEY)
                await queue.consume(_relay)
                logger.info("[LIVE] relaying notification.created to open sockets")
                await stop.wait()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[LIVE] RabbitMQ unavailable ({exc}); retrying in {RETRY_DELAY_SECONDS}s")
            try:
                await asyncio.wait_for(stop.wait(), timeout=RETRY_DELAY_SECONDS)
            except asyncio.TimeoutError:
                pass
