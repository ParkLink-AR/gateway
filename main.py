import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app import live
from app.config import settings
from app.logger import setup_logger
from app.middleware import AccessLogMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from app.proxy import SERVICE_BASE_URL_ATTR
from app.rabbitmq import rabbitmq_client
from app.routes import register_routes
from app.monitoring import init_monitoring

setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=settings.UPSTREAM_TIMEOUT_SECONDS)
    await rabbitmq_client.connect()
    stop_live = asyncio.Event()
    live_task = asyncio.create_task(live.run_consumer(stop_live))
    logger.info("[STARTUP] ParkLink Gateway iniciado")
    yield
    stop_live.set()
    live_task.cancel()
    try:
        await live_task
    except asyncio.CancelledError:
        pass
    await app.state.http_client.aclose()
    await rabbitmq_client.close()
    logger.info("[SHUTDOWN] ParkLink Gateway detenido")


init_monitoring()

app = FastAPI(title="ParkLink Gateway", version="1.0.0", lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_routes(app)
app.add_api_websocket_route("/notifications/live", live.live_endpoint)


@app.get("/livez", tags=["health"])
def livez():
    """El proceso HTTP está vivo y puede recibir requests."""
    return {"status": "alive"}


@app.get("/readyz", tags=["health"])
def readyz():
    """El gateway puede operar. No implica que los microservicios downstream
    estén sanos -- eso lo reporta /health con más detalle."""
    return {"status": "ready"}


@app.get("/health", tags=["health"])
def health():
    configured_services = {
        service: bool(getattr(settings, attr, ""))
        for service, attr in SERVICE_BASE_URL_ATTR.items()
    }
    return {
        "status": "ok",
        "rabbitmq": "connected" if rabbitmq_client.is_connected else "disconnected",
        "live_connections": live.hub.connection_count(),
        "services_configured": configured_services,
    }
