"""Error reports to Sentry. Without SENTRY_DSN it stays off (development, tests): nothing is
sent and sentry_sdk isn't even imported."""
from __future__ import annotations

import os

SERVICE_NAME = "gateway"


def init_monitoring() -> None:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return
    import sentry_sdk

    # The FastAPI/Starlette integrations turn on by themselves: unhandled exceptions in a
    # request are reported with it. Errors only -- no tracing, no personal data.
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        server_name=SERVICE_NAME,
        traces_sample_rate=0,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("service", SERVICE_NAME)
