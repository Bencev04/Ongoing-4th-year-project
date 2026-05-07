import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

# Configure structured logging BEFORE importing FastAPI/Uvicorn
from common.logging_config import configure_logging, get_logger
from common.metrics_config import PrometheusMiddleware, get_metrics

configure_logging(
    service_name="notification-service",
    level=os.environ.get("LOG_LEVEL", "INFO"),
    environment=os.environ.get("ENVIRONMENT", "development"),
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
)

logger = get_logger(__name__)

# Now import FastAPI and other dependencies
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.config import settings
from common.exceptions import BaseServiceException
from common.redis import close_redis, get_redis

from .api.routes import router
from .api.webhooks import router as webhook_router
from .logic.scheduler import scheduler_loop
from .service_client import close_http_client, init_http_client

_debug = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")

app = FastAPI(
    title="Notification Service",
    description="Manages WhatsApp and email notifications for the CRM Calendar platform.",
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
    docs_url="/docs" if _debug else None,
    redoc_url="/redoc" if _debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)
app.add_middleware(PrometheusMiddleware, service_name="notification-service")

_scheduler_task: asyncio.Task | None = None


@app.exception_handler(BaseServiceException)
async def service_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code, "details": exc.details},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "INTERNAL_ERROR"},
    )


@app.on_event("startup")
async def startup_event():
    global _scheduler_task
    await init_http_client()
    _scheduler_task = asyncio.create_task(scheduler_loop())
    logger.info("Notification Service started — scheduler running")


@app.on_event("shutdown")
async def shutdown_event():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    await close_http_client()
    await close_redis()
    logger.info("Notification Service shut down")


app.include_router(router)
app.include_router(webhook_router)


@app.get("/")
async def root():
    return {"service": "notification-service", "version": "1.0.0", "status": "running"}


# Metrics endpoint for Prometheus
@app.get("/metrics")
async def metrics():
    """Return Prometheus metrics."""
    return get_metrics()


@app.get("/api/v1/health")
async def health():
    return {"status": "healthy", "service": "notification-service"}


@app.get("/api/v1/ready")
async def ready():
    try:
        redis_client = await get_redis()
        await redis_client.ping()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis is unavailable",
        ) from exc

    return {
        "status": "ready",
        "service": "notification-service",
        "redis": "ok",
        "smtp_configured": bool(settings.smtp_host),
    }
