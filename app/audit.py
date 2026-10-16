"""Records what admins change from the panel: after every successful write on an ADMIN
route, the gateway tells auth-service who did what (POST /internal/admin-audit), so every
service's admin actions end up in one log without each one keeping its own. Best effort --
a failure to record never fails the action itself."""

from __future__ import annotations

import asyncio
import json

import httpx
from loguru import logger

from app.config import settings

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Request-body fields worth keeping in the log: why, what decision, how much. Anything else
# (passwords, files, free text beyond these) is left out.
SUMMARY_FIELDS = (
    "reason", "note", "notes", "status", "decision", "action", "amount", "refund_amount",
    "resolution", "commission_rate_bp", "title", "audience", "is_active", "role", "username",
    "exited_at",
)


def summarize(body: bytes) -> str | None:
    """'reason: ... · amount: ...' from a JSON body's interesting fields."""
    if not body:
        return None
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    parts = [f"{key}: {data[key]}" for key in SUMMARY_FIELDS if key in data and data[key] not in (None, "")]
    return " · ".join(parts)[:2000] or None


async def _send(client: httpx.AsyncClient, entry: dict) -> None:
    try:
        await client.post(
            f"{settings.AUTH_SERVICE_URL}/internal/admin-audit",
            json=entry,
            headers={"x-gateway-secret": settings.GATEWAY_INTERNAL_SECRET},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        logger.warning(f"[AUDIT] could not record {entry['method']} {entry['path']}: {exc}")


def record_admin_action(
    client: httpx.AsyncClient,
    *,
    admin_id: str | None,
    admin_username: str | None,
    method: str,
    path: str,
    status_code: int,
    body: bytes,
) -> None:
    """Fire-and-forget: only successful writes are logged."""
    if method not in WRITE_METHODS or status_code >= 400:
        return
    entry = {
        "admin_id": admin_id,
        "admin_username": admin_username,
        "method": method,
        "path": path[:300],
        "status_code": status_code,
        "summary": summarize(body),
    }
    asyncio.get_running_loop().create_task(_send(client, entry))
