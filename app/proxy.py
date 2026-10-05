from __future__ import annotations

import uuid
from enum import Enum
from typing import Callable

import httpx
from fastapi import Request, Response
from loguru import logger

from app.config import settings
from app.problem_json import problem_response
from app.security import InvalidTokenError, NotAdminError, authenticate, authenticate_admin

# Headers that are per-hop or get recomputed by httpx/the ASGI server; forwarding
# them verbatim (in either direction) would corrupt the proxied response.
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


class AuthMode(str, Enum):
    PUBLIC = "public"
    REQUIRED = "required"
    # Same as REQUIRED, plus the token's role claim must be "admin" -- see
    # app.security.authenticate_admin for how that's minted/checked.
    ADMIN = "admin"


# service key -> settings attribute holding its base URL
SERVICE_BASE_URL_ATTR = {
    "auth": "AUTH_SERVICE_URL",
    "parking": "PARKING_SERVICE_URL",
    "payment": "PAYMENT_SERVICE_URL",
    "booking": "BOOKING_SERVICE_URL",
    "notifications": "NOTIFICATIONS_SERVICE_URL",
}


def _service_base_url(service: str) -> str:
    return getattr(settings, SERVICE_BASE_URL_ATTR[service], "")


def _downstream_path(service: str, gateway_path: str) -> str:
    # payment-service mounts its API under /api/payments/*, everything else
    # mirrors the gateway path 1:1.
    if service == "payment":
        return gateway_path.replace("/payments", "/api/payments", 1)
    return gateway_path


def _forward_request_headers(request: Request, user_id: str | None, admin_role: str | None = None) -> dict[str, str]:
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    headers["x-request-id"] = request_id
    # Strip any incoming untrusted client-supplied identity/internal headers to prevent spoofing
    headers.pop("x-user-id", None)
    headers.pop("x-admin-role", None)
    headers.pop("x-internal-key", None)
    headers.pop("x-gateway-secret", None)
    # Inject legitimate gateway authentication header
    if settings.GATEWAY_INTERNAL_SECRET:
        headers["x-gateway-secret"] = settings.GATEWAY_INTERNAL_SECRET
    if user_id is not None:
        # Downstream services trust this instead of re-verifying the JWT
        # themselves -- safe because each one only accepts requests carrying
        # x-gateway-secret (set above) or the service-to-service key. The
        # original Authorization header is still forwarded as-is for services
        # that want to check it.
        headers["x-user-id"] = user_id
    if admin_role is not None:
        # Set for any ParkLink admin token (ADMIN routes, and REQUIRED routes the admin
        # panel shares with the app) -- lets services let staff past per-user ownership
        # checks, and gate SUPERADMIN-only actions (e.g. booking-service's commission
        # settings) without calling back into auth-service to look it up.
        headers["x-admin-role"] = admin_role
    return headers


def _forward_response_headers(response: httpx.Response) -> dict[str, str]:
    return {k: v for k, v in response.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}


def make_proxy_handler(service: str, auth_mode: AuthMode) -> Callable:
    async def handler(request: Request) -> Response:
        user_id: str | None = None
        admin_role: str | None = None
        if auth_mode is AuthMode.REQUIRED:
            try:
                user_id, admin_role = authenticate(request.headers.get("authorization"))
            except InvalidTokenError as exc:
                return problem_response(request, 401, "Unauthorized", str(exc))
        elif auth_mode is AuthMode.ADMIN:
            try:
                user_id, admin_role = authenticate_admin(request.headers.get("authorization"))
            except InvalidTokenError as exc:
                return problem_response(request, 401, "Unauthorized", str(exc))
            except NotAdminError as exc:
                return problem_response(request, 403, "Forbidden", str(exc))

        base_url = _service_base_url(service)
        if not base_url:
            return problem_response(
                request,
                503,
                "Service Unavailable",
                f"{service}-service is not deployed/configured yet",
            )

        downstream_path = _downstream_path(service, request.url.path)
        url = f"{base_url}{downstream_path}"
        body = await request.body()
        client: httpx.AsyncClient = request.app.state.http_client

        try:
            upstream_response = await client.request(
                request.method,
                url,
                params=request.query_params,
                content=body,
                headers=_forward_request_headers(request, user_id, admin_role),
            )
        except httpx.TimeoutException:
            logger.warning(f"[PROXY] Timeout forwarding {request.method} {url}")
            return problem_response(request, 504, "Gateway Timeout", f"{service}-service did not respond in time")
        except httpx.ConnectError as exc:
            logger.warning(f"[PROXY] Connection error forwarding {request.method} {url}: {exc}")
            return problem_response(request, 503, "Service Unavailable", f"{service}-service is unreachable")

        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=_forward_response_headers(upstream_response),
            media_type=upstream_response.headers.get("content-type"),
        )

    return handler
