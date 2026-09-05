from collections import defaultdict
import time
import uuid

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.problem_json import problem_response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory rate limiter using sliding window per IP to defend against brute-force and DoS."""

    def __init__(self, app, default_limit: int = 120, default_window: int = 60):
        super().__init__(app)
        self.default_limit = default_limit
        self.default_window = default_window
        self.requests_map: dict[str, list[float]] = defaultdict(list)
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
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)
        now = time.time()
        path = request.url.path

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
