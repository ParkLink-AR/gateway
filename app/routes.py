from __future__ import annotations

from dataclasses import dataclass
from typing import List

from fastapi import FastAPI

from app.proxy import AuthMode, make_proxy_handler

PUBLIC = AuthMode.PUBLIC
REQUIRED = AuthMode.REQUIRED


@dataclass(frozen=True)
class ProxyRoute:
    methods: List[str]
    path: str
    service: str
    auth: AuthMode


# Order matters: more specific paths must come before catch-alls/overlapping
# prefixes so Starlette matches the right one first (e.g.
# "/parking-spots/{id}/availability" has to be registered before parking's
# generic "/parking-spots/{id}").
ROUTE_TABLE: list[ProxyRoute] = [
    # -- auth-service --------------------------------------------------
    ProxyRoute(["POST"], "/auth/register", "auth", PUBLIC),
    ProxyRoute(["POST"], "/auth/login", "auth", PUBLIC),
    ProxyRoute(["POST"], "/auth/refresh", "auth", PUBLIC),
    ProxyRoute(["POST"], "/auth/logout", "auth", PUBLIC),
    ProxyRoute(["GET"], "/auth/sessions", "auth", REQUIRED),
    ProxyRoute(["DELETE"], "/auth/sessions/{session_id}", "auth", REQUIRED),
    ProxyRoute(["POST"], "/auth/email-verification/request", "auth", PUBLIC),
    ProxyRoute(["POST"], "/auth/email-verification/confirm", "auth", PUBLIC),
    ProxyRoute(["POST"], "/auth/registration/email/request", "auth", PUBLIC),
    ProxyRoute(["POST"], "/auth/registration/email/confirm", "auth", PUBLIC),
    ProxyRoute(["POST"], "/auth/registration/phone/request", "auth", PUBLIC),
    ProxyRoute(["POST"], "/auth/registration/phone/confirm", "auth", PUBLIC),
    ProxyRoute(["POST"], "/auth/password-reset/request", "auth", PUBLIC),
    ProxyRoute(["POST"], "/auth/password-reset/confirm", "auth", PUBLIC),
    # -- users (identity lives in auth-service; sub-resources belong to
    #    whichever service owns them) -----------------------------------
    ProxyRoute(["GET"], "/users/{id}/parking-spots", "parking", PUBLIC),
    ProxyRoute(["GET"], "/users/{id}/bookings/history", "booking", REQUIRED),
    ProxyRoute(["GET"], "/users/{id}/reviews", "booking", REQUIRED),
    ProxyRoute(["POST"], "/users/{id}/avatar", "auth", REQUIRED),
    ProxyRoute(["POST"], "/users/{id}/email/confirm", "auth", REQUIRED),
    ProxyRoute(["POST"], "/users/{id}/email", "auth", REQUIRED),
    ProxyRoute(["POST"], "/users/{id}/phone/confirm", "auth", REQUIRED),
    ProxyRoute(["POST"], "/users/{id}/phone", "auth", REQUIRED),
    ProxyRoute(["GET"], "/users/{id}/public-profile", "auth", REQUIRED),
    ProxyRoute(["GET"], "/users/{id}", "auth", REQUIRED),
    ProxyRoute(["PUT"], "/users/{id}", "auth", REQUIRED),
    ProxyRoute(["DELETE"], "/users/{id}", "auth", REQUIRED),
    # -- booking-service (owns these /parking-spots/{id}/* sub-resources) --
    ProxyRoute(["GET"], "/parking-spots/{id}/bookings/detailed", "booking", REQUIRED),
    ProxyRoute(["GET"], "/parking-spots/{id}/bookings", "booking", REQUIRED),
    ProxyRoute(["GET"], "/parking-spots/{id}/reviews", "booking", PUBLIC),
    ProxyRoute(["POST"], "/bookings/{id}/confirm", "booking", REQUIRED),
    ProxyRoute(["POST"], "/bookings/{id}/approve", "booking", REQUIRED),
    ProxyRoute(["POST"], "/bookings/{id}/reject", "booking", REQUIRED),
    ProxyRoute(["POST"], "/bookings/{id}/reviews", "booking", REQUIRED),
    ProxyRoute(["POST"], "/bookings/{id}/cancel", "booking", REQUIRED),
    ProxyRoute(["GET"], "/bookings/{id}/reviews", "booking", REQUIRED),
    ProxyRoute(["GET"], "/bookings/{id}", "booking", REQUIRED),
    ProxyRoute(["POST"], "/bookings", "booking", REQUIRED),
    # -- parking-service ------------------------------------------------
    ProxyRoute(["GET"], "/geocode/reverse", "parking", PUBLIC),
    ProxyRoute(["GET"], "/geocode", "parking", PUBLIC),
    ProxyRoute(["GET"], "/parking-spots/search", "parking", PUBLIC),
    ProxyRoute(["POST"], "/parking-spots", "parking", REQUIRED),
    ProxyRoute(["GET"], "/parking-spots/{id}/availability", "parking", PUBLIC),
    ProxyRoute(["GET"], "/parking-spots/{id}/photos", "parking", PUBLIC),
    ProxyRoute(["POST"], "/parking-spots/{id}/photos", "parking", REQUIRED),
    ProxyRoute(["DELETE"], "/parking-spots/{id}/photos", "parking", REQUIRED),
    ProxyRoute(["PUT"], "/parking-spots/{id}/photos/order", "parking", REQUIRED),
    ProxyRoute(["PATCH"], "/parking-spots/{id}/status", "parking", REQUIRED),
    ProxyRoute(["PUT"], "/parking-spots/{id}/pricing", "parking", REQUIRED),
    ProxyRoute(["PUT"], "/parking-spots/{id}/schedule", "parking", REQUIRED),
    ProxyRoute(["GET"], "/parking-spots/{id}", "parking", PUBLIC),
    ProxyRoute(["PUT"], "/parking-spots/{id}", "parking", REQUIRED),
    ProxyRoute(["DELETE"], "/parking-spots/{id}", "parking", REQUIRED),
    ProxyRoute(["GET"], "/favorites/ids", "parking", REQUIRED),
    ProxyRoute(["GET"], "/favorites", "parking", REQUIRED),
    ProxyRoute(["POST"], "/favorites", "parking", REQUIRED),
    ProxyRoute(["DELETE"], "/favorites/{parking_spot_id}", "parking", REQUIRED),
    # -- payment-service (mounted at /api/payments/* downstream) --------
    ProxyRoute(["POST"], "/payments/create-preference", "payment", REQUIRED),
    ProxyRoute(["POST"], "/payments/webhook", "payment", PUBLIC),
    # REQUIRED, not PUBLIC: this looks up a payment (amount, payer email) by
    # external_reference/paymentId with no ownership check on payment-service's
    # side, so anyone with a reference could query someone else's payment.
    # Mobile's request() always attaches the bearer token when there is one
    # (see pending.tsx's polling loop), so this doesn't break that flow.
    ProxyRoute(["POST"], "/payments/verify-status", "payment", REQUIRED),
    ProxyRoute(["GET"], "/payments/external-reference/{external_reference}", "payment", REQUIRED),
    ProxyRoute(["GET"], "/payments/{payment_id}", "payment", REQUIRED),
    # -- notifications-service ----------------------------------------
    # Only the device-token registry is exposed; domain notifications flow
    # over RabbitMQ, not HTTP, so the client never proxies anything else here.
    ProxyRoute(["DELETE"], "/notifications/tokens/{token}", "notifications", REQUIRED),
    ProxyRoute(["PUT"], "/notifications/tokens", "notifications", REQUIRED),
]


def register_routes(app: FastAPI) -> None:
    for route in ROUTE_TABLE:
        app.add_route(
            route.path,
            make_proxy_handler(route.service, route.auth),
            methods=route.methods,
        )
