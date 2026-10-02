from __future__ import annotations

from dataclasses import dataclass
from typing import List

from fastapi import FastAPI

from app.proxy import AuthMode, make_proxy_handler

PUBLIC = AuthMode.PUBLIC
REQUIRED = AuthMode.REQUIRED
ADMIN = AuthMode.ADMIN


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
    # ParkLink-staff login -- a completely separate identity system from the
    # app's own users (see app/models/admin_account.py in auth-service): no
    # relation to /auth/login above, own username/password, own JWT issuance.
    # PUBLIC like /auth/login, for the same reason (you need a token before
    # you can be authenticated).
    ProxyRoute(["POST"], "/admin/auth/login", "auth", PUBLIC),
    # -- users (identity lives in auth-service; sub-resources belong to
    #    whichever service owns them) -----------------------------------
    ProxyRoute(["GET"], "/users/{id}/parking-spots", "parking", PUBLIC),
    ProxyRoute(["GET"], "/users/{id}/bookings/history", "booking", REQUIRED),
    # Owner's own "Finanzas" history -- PAID settlements only (a still-PENDING draft is
    # hidden even from its own owner, see booking-service's GetOwnSettlementUseCase).
    ProxyRoute(["GET"], "/users/{id}/settlements", "booking", REQUIRED),
    # Every support ticket this user has ever opened, across every booking -- the mobile
    # app's in-app notification feed uses this to surface support.ticket_replied without a
    # dedicated per-ticket poll.
    ProxyRoute(["GET"], "/users/{id}/tickets", "booking", REQUIRED),
    ProxyRoute(["GET"], "/users/{id}/reviews", "booking", REQUIRED),
    ProxyRoute(["POST"], "/users/{id}/avatar", "auth", REQUIRED),
    ProxyRoute(["POST"], "/users/{id}/email/confirm", "auth", REQUIRED),
    ProxyRoute(["POST"], "/users/{id}/email", "auth", REQUIRED),
    ProxyRoute(["POST"], "/users/{id}/phone/confirm", "auth", REQUIRED),
    ProxyRoute(["POST"], "/users/{id}/phone", "auth", REQUIRED),
    ProxyRoute(["GET"], "/users/{id}/public-profile", "auth", REQUIRED),
    # Owner payout bank details -- self-service, same reasoning as email/phone/
    # avatar above: a user managing their own sub-resource. (There's also an
    # internal auth-service endpoint, /internal/users/{id}/payout-status, used
    # service-to-service by parking-service; it deliberately has no gateway
    # route and bypasses this proxy entirely, same convention as other
    # internal-only endpoints in this codebase.)
    ProxyRoute(["GET"], "/users/{id}/payout-info", "auth", REQUIRED),
    ProxyRoute(["PUT"], "/users/{id}/payout-info", "auth", REQUIRED),
    ProxyRoute(["POST"], "/users/{id}/password/verify", "auth", REQUIRED),
    ProxyRoute(["PUT"], "/users/{id}/password", "auth", REQUIRED),
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
    ProxyRoute(["POST"], "/bookings/{id}/verify-code", "booking", REQUIRED),
    ProxyRoute(["POST"], "/bookings/{id}/reviews", "booking", REQUIRED),
    ProxyRoute(["POST"], "/bookings/{id}/cancel", "booking", REQUIRED),
    ProxyRoute(["POST"], "/bookings/{id}/messages", "booking", REQUIRED),
    ProxyRoute(["GET"], "/bookings/{id}/reviews", "booking", REQUIRED),
    ProxyRoute(["GET"], "/bookings/{id}/messages", "booking", REQUIRED),
    ProxyRoute(["POST"], "/bookings/{id}/tickets", "booking", REQUIRED),
    ProxyRoute(["GET"], "/bookings/{id}/tickets", "booking", REQUIRED),
    ProxyRoute(["GET"], "/bookings/{id}", "booking", REQUIRED),
    ProxyRoute(["POST"], "/bookings", "booking", REQUIRED),
    # Read-only, non-admin: mobile needs the current commission rate to show a price
    # breakdown (owner receives X, driver pays X + commission) when creating a spot and
    # when viewing one.
    ProxyRoute(["GET"], "/settings/commission", "booking", REQUIRED),
    # A booking-scoped support ticket, once opened, is addressed by its own id
    # rather than nested under /bookings/{id} -- same shape as /tickets/{id}/*.
    ProxyRoute(["GET"], "/tickets/{id}/messages", "booking", REQUIRED),
    ProxyRoute(["POST"], "/tickets/{id}/messages", "booking", REQUIRED),
    ProxyRoute(["GET"], "/tickets/{id}", "booking", REQUIRED),
    # Owner's own settlement detail -- REQUIRED, not ADMIN: booking-service's
    # GetOwnSettlementUseCase itself enforces the caller owns it (403 otherwise), same
    # "gateway just authenticates, the service checks resource ownership" pattern as
    # /tickets/{id} above.
    ProxyRoute(["GET"], "/settlements/{id}", "booking", REQUIRED),
    # -- support tickets, ParkLink-staff side (admin-dashboard) -- ADMIN, not
    # REQUIRED: only a token with role:"admin" may reach these (see
    # app.security.authenticate_admin). --------------------------------
    ProxyRoute(["GET"], "/admin/tickets/{id}/messages", "booking", ADMIN),
    ProxyRoute(["POST"], "/admin/tickets/{id}/messages", "booking", ADMIN),
    ProxyRoute(["PATCH"], "/admin/tickets/{id}/status", "booking", ADMIN),
    ProxyRoute(["GET"], "/admin/tickets/{id}", "booking", ADMIN),
    ProxyRoute(["GET"], "/admin/tickets", "booking", ADMIN),
    # -- owner payouts/settlements queue, ParkLink-staff side -- same ADMIN
    # reasoning as the support tickets block above. Payouts accumulate per
    # booking automatically, but are only ever paid out in a batch per owner
    # (see booking-service's DraftSettlementUseCase/ConfirmSettlementUseCase):
    # an admin drafts a settlement (freezes the current pending total), then
    # confirms it (optional multipart receipt upload) once the transfer
    # actually went out -- draft/confirm/cancel replace the old single-payout
    # mark-paid action entirely.
    ProxyRoute(["GET"], "/admin/payouts/{id}", "booking", ADMIN),
    ProxyRoute(["GET"], "/admin/payouts", "booking", ADMIN),
    # Aggregate view of everything an owner has received across all their
    # spots -- distinct prefix from /admin/payouts above, no ordering conflict.
    ProxyRoute(["GET"], "/admin/owners/{id}/bookings", "booking", ADMIN),
    # Who currently has an unsettled balance -- the admin panel's starting
    # point for deciding who to pay next.
    ProxyRoute(["GET"], "/admin/owners/pending-balances", "booking", ADMIN),
    # Phase 1 (freeze the amount) -- no proof yet, see comment above.
    ProxyRoute(["POST"], "/admin/owners/{id}/settlements", "booking", ADMIN),
    # Phase 2 (confirm the transfer went out, optional receipt) and the
    # mistake-undo escape hatch -- registered before the bare
    # /admin/settlements/{id}, same {id}/sub-action-before-{id} convention as
    # the tickets/payouts blocks above.
    ProxyRoute(["POST"], "/admin/settlements/{id}/confirm", "booking", ADMIN),
    ProxyRoute(["POST"], "/admin/settlements/{id}/cancel", "booking", ADMIN),
    ProxyRoute(["GET"], "/admin/settlements/{id}", "booking", ADMIN),
    ProxyRoute(["GET"], "/admin/settlements", "booking", ADMIN),
    # Admin-configurable commission rate used when computing payouts.
    ProxyRoute(["GET"], "/admin/settings/commission", "booking", ADMIN),
    ProxyRoute(["PUT"], "/admin/settings/commission", "booking", ADMIN),
    # -- auth-service, ParkLink-staff side (admin-dashboard) -- ADMIN, not
    # REQUIRED, same reasoning as the /admin/tickets/* block above: staff
    # searching/viewing user accounts to administer payouts. {id}-specific
    # route registered before the bare list, same convention as elsewhere.
    ProxyRoute(["GET"], "/admin/users/{id}", "auth", ADMIN),
    ProxyRoute(["GET"], "/admin/users", "auth", ADMIN),
    # Admin-account management (creating/listing/deactivating ParkLink-staff
    # accounts). Gateway only enforces the blanket role:"admin" claim here --
    # the finer SUPERADMIN-only check happens inside auth-service itself
    # (see app/api/admin_auth.py), same pattern as this codebase already uses
    # wherever an endpoint needs more than the gateway's binary ADMIN gate.
    ProxyRoute(["POST"], "/admin/accounts", "auth", ADMIN),
    ProxyRoute(["GET"], "/admin/accounts", "auth", ADMIN),
    ProxyRoute(["POST"], "/admin/accounts/{id}/password", "auth", ADMIN),
    ProxyRoute(["PATCH"], "/admin/accounts/{id}", "auth", ADMIN),
    # No superadmin gate on this one (see auth-service's get_admin_account) -- any admin
    # can resolve another admin id's username, e.g. a settlement's "creado por"/"pagado por".
    ProxyRoute(["GET"], "/admin/accounts/{id}", "auth", ADMIN),
    # -- parking-service ------------------------------------------------
    ProxyRoute(["GET"], "/geocode/reverse", "parking", PUBLIC),
    ProxyRoute(["GET"], "/geocode", "parking", PUBLIC),
    ProxyRoute(["GET"], "/parking-spots/search", "parking", PUBLIC),
    # Batch detail lookup (?ids=a,b,c) -- same auth level as the single-spot
    # GET /parking-spots/{id} below, since it returns the same public data,
    # just for several spots in one request instead of one per id.
    ProxyRoute(["GET"], "/parking-spots", "parking", PUBLIC),
    ProxyRoute(["POST"], "/parking-spots", "parking", REQUIRED),
    ProxyRoute(["GET"], "/parking-spots/{id}/availability", "parking", PUBLIC),
    # "Estadía" (day/week/month rental): a read-only quote, same auth level as
    # .../availability above -- it prices and validates a stay but doesn't book
    # anything. Also called directly (bypassing this gateway) by booking-service
    # when it actually creates a STAY booking, to confirm the amount server-side.
    ProxyRoute(["GET"], "/parking-spots/{id}/stays/quote", "parking", PUBLIC),
    # Calendario de disponibilidad para elegir fecha de inicio de estadía --
    # mismo nivel de auth que .../stays/quote y .../availability, sólo lectura.
    ProxyRoute(["GET"], "/parking-spots/{id}/stays/availability", "parking", PUBLIC),
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
    ProxyRoute(["GET"], "/payments/metrics", "payment", REQUIRED),
    ProxyRoute(["POST"], "/payments/create-preference", "payment", REQUIRED),
    ProxyRoute(["POST"], "/payments/webhook", "payment", PUBLIC),
    ProxyRoute(["GET"], "/payments/redirect", "payment", PUBLIC),
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
