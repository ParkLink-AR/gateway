from collections import defaultdict
import time
import uuid

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.problem_json import problem_response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory rate limiter using sliding window per IP to defend against brute-force and DoS."""

    # How often to sweep requests_map for stale keys (clients that stopped
    # sending requests), so memory doesn't grow forever with one-off/spoofed
    # IPs. Anything not touched in this long is expired for every window we
    # track (the largest configured window is 60s), so it's safe to drop.
    SWEEP_INTERVAL_SECONDS = 300

    def __init__(self, app, default_limit: int = 120, default_window: int = 60):
        super().__init__(app)
        self.default_limit = default_limit
        self.default_window = default_window
        self.requests_map: dict[str, list[float]] = defaultdict(list)
        self._last_sweep = time.time()
        # Sensitive routes with strict limits: (max_requests, window_seconds)
        self.sensitive_routes = {
            "/auth/login": (10, 60),
            "/auth/register": (10, 60),
            "/auth/password-reset/request": (5, 60),
            "/auth/password-reset/confirm": (5, 60),
            "/auth/registration/email/request": (5, 60),
            "/auth/registration/phone/request": (5, 60),
            "/payments/create-preference": (20, 60),
        }

    def _get_client_ip(self, request: Request) -> str:
        # Cloudflare (used locally via `cloudflared tunnel` to expose the gateway during
        # dev/testing) always sets this to the real originating client's address, not
        # forgeable by the client since only Cloudflare's own edge sets it -- checked first
        # so every device testing through the same tunnel gets its own bucket instead of
        # all of them colliding on the tunnel's single apparent last hop below.
        cf_connecting_ip = request.headers.get("cf-connecting-ip")
        if cf_connecting_ip:
            return cf_connecting_ip.strip()
        # Render (our only reverse proxy in front of the gateway in production) appends its
        # own resolved address to X-Forwarded-For rather than replacing it, so
        # the FIRST entry is whatever the client sent and can't be trusted --
        # a client can put anything there to dodge the limit. The LAST entry
        # is the one Render itself added, which the client can't forge.
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[-1].strip()
        return request.client.host if request.client else "unknown"

    def _sweep_stale_entries(self, now: float) -> None:
        if now - self._last_sweep < self.SWEEP_INTERVAL_SECONDS:
            return
        self._last_sweep = now
        max_window = max([self.default_window, *(w for _, w in self.sensitive_routes.values())])
        stale_keys = [
            key for key, timestamps in self.requests_map.items()
            if not timestamps or now - timestamps[-1] > max_window
        ]
        for key in stale_keys:
            del self.requests_map[key]

    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)
        now = time.time()
        path = request.url.path

        self._sweep_stale_entries(now)

        max_req, window = self.sensitive_routes.get(
            path, (self.default_limit, self.default_window)
        )
        key = f"{client_ip}:{path}" if path in self.sensitive_routes else client_ip

        # Clean timestamps older than window
        timestamps = [ts for ts in self.requests_map[key] if now - ts < window]
        if len(timestamps) >= max_req:
            logger.warning(
                f"[RATE_LIMIT] Client {client_ip} exceeded limit on {path} ({len(timestamps)}/{max_req})"
            )
            return problem_response(
                request,
                429,
                "Too Many Requests",
                "Has superado el límite de solicitudes. Por favor, intentá nuevamente en unos momentos.",
            )

        timestamps.append(now)
        self.requests_map[key] = timestamps

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to all HTTP responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates X-Request-Id and logs one line per request, so a
    single request can be traced across the gateway and (once other services
    read the header) downstream logs too."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        started_at = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - started_at) * 1000
        response.headers["x-request-id"] = request_id
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} "
            f"-> {response.status_code} ({duration_ms:.1f}ms)"
        )
        return response
