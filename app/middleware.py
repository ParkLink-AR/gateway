import time
import uuid

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


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
