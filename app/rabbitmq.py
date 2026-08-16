from __future__ import annotations

import json

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractRobustConnection
from loguru import logger

from app.config import settings

# Well-known topic exchange shared by the whole platform. booking-service and
# payment-service publish domain events here (booking.confirmed,
# booking.reminder, booking.cancelled, payment.completed -- see
# notifications-service/README.md) and notifications-service binds queues to
# it. The gateway doesn't consume anything itself; it just owns declaring the
# exchange so it exists before those services come online, and exposes
# publish_event() for anything the gateway itself needs to announce.
EVENTS_EXCHANGE_TYPE = aio_pika.ExchangeType.TOPIC


class RabbitMQClient:
    def __init__(self, url: str, exchange_name: str) -> None:
        self._url = url
        self._exchange_name = exchange_name
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    async def connect(self) -> None:
        try:
            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = await self._connection.channel()
            self._exchange = await self._channel.declare_exchange(
                self._exchange_name, EVENTS_EXCHANGE_TYPE, durable=True
            )
            logger.info(f"[RABBITMQ] Connected, exchange '{self._exchange_name}' ready")
        except Exception as exc:
            # RabbitMQ being down must not take the HTTP proxy down with it.
            logger.warning(f"[RABBITMQ] Could not connect ({exc}); continuing without it")
            self._connection = None
            self._channel = None
            self._exchange = None

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            logger.info("[RABBITMQ] Connection closed")

    async def publish_event(self, routing_key: str, payload: dict) -> bool:
        """Publishes a JSON message to the shared topic exchange. Returns
        False (and logs) instead of raising if RabbitMQ isn't available."""
        if self._exchange is None:
            logger.warning(f"[RABBITMQ] Dropping event '{routing_key}': not connected")
            return False

        message = aio_pika.Message(
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=routing_key)
        return True


rabbitmq_client = RabbitMQClient(settings.RABBITMQ_URL, settings.EVENTS_EXCHANGE)
