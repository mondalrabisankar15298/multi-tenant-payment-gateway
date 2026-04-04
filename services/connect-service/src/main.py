import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles

from .database import get_pool, get_core_primary_pool, get_core_replica_pool, close_all_pools
from .consumers.db_sync_consumer import start_db_sync_consumer
from .consumers.tp_webhook_consumer import start_tp_webhook_consumer
from .routers import oauth, bulk_api, tp_webhooks, consumer_management, analytics
from .middleware.request_id import RequestIdMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .utils.logger import setup_logging, get_logger
from .config import settings
from prometheus_client import make_asgi_app

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all DB pools and start consumers
    await get_pool()              # Read DB (for DB sync consumer — unchanged)
    await get_core_primary_pool()  # Core DB Primary (writes)
    await get_core_replica_pool()  # Core DB Replica (Bulk API reads)

    logger.info("All database pools initialized")

    shutdown_event = asyncio.Event()

    def handle_task_result(task: asyncio.Task):
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Background consumer task failed: {e}", exc_info=True)

    # Start Kafka consumers as background tasks
    db_sync_task = asyncio.create_task(start_db_sync_consumer(shutdown_event))
    db_sync_task.add_done_callback(handle_task_result)

    # Third-party webhook consumer (runs in thread to avoid blocking event loop)
    tp_webhook_task = asyncio.get_running_loop().run_in_executor(None, start_tp_webhook_consumer)

    yield

    # Shutdown
    shutdown_event.set()
    await asyncio.gather(db_sync_task, return_exceptions=True)
    await close_all_pools()
    logger.info("All pools closed, shutdown complete")


app = FastAPI(
    title="Connect Service — Third-Party Gateway",
    description="System 2 — Event Engine + Third-Party API Gateway (OAuth, Bulk API, Webhooks, Analytics)",
    version="2.0.0",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"Unhandled exception [request_id={request_id}]: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "request_id": request_id,
        },
    )


# ─── Middleware (order matters: first added = outermost) ──

# Request ID — outermost, adds X-Request-ID to all responses
app.add_middleware(RequestIdMiddleware)

# Rate Limiting — applies to /api/v1/third-party/ routes
app.add_middleware(RateLimitMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Admin-Key", "X-Merchant-ID"],
)

# Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# ─── Admin UI (Phase 6) ──────────────────────────────────
# Serve the built React Admin UI on /admin path
UI_DIST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "dist")
if os.path.isdir(UI_DIST_PATH):
    app.mount("/admin", StaticFiles(directory=UI_DIST_PATH, html=True), name="admin-ui")
    logger.info(f"Admin UI served from {UI_DIST_PATH}")
else:
    logger.warning(f"Admin UI dist not found at {UI_DIST_PATH}, /admin will return 404")

# ─── Admin UI (Phase 6) ──────────────────────────────────
# Serve the built React Admin UI on /admin path
UI_DIST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "dist")
if os.path.isdir(UI_DIST_PATH):
    app.mount("/admin", StaticFiles(directory=UI_DIST_PATH, html=True), name="admin-ui")
    logger.info(f"Admin UI served from {UI_DIST_PATH}")
else:
    logger.warning(f"Admin UI dist not found at {UI_DIST_PATH}, /admin will return 404")

# ─── Routers ─────────────────────────────────────────────

# OAuth (public — no auth required)
app.include_router(oauth.router)

# Third-party Bulk API (Bearer token required)
app.include_router(bulk_api.router)

# Third-party Webhook management (Bearer token + webhooks:manage scope)
app.include_router(tp_webhooks.router)

# Admin — Consumer management (X-Admin-Key required)
app.include_router(consumer_management.router)

# Admin — Analytics (X-Admin-Key required)
app.include_router(analytics.router)


# ─── Health Check ────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check():
    health_status = {
        "status": "healthy",
        "service": "connect-service",
        "version": "2.0.0",
        "components": {},
    }

    # Check Read DB
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        health_status["components"]["read_db"] = "ok"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["components"]["read_db"] = f"error: {str(e)}"

    # Check Core DB Primary
    try:
        pool = await get_core_primary_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        health_status["components"]["core_primary"] = "ok"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["components"]["core_primary"] = f"error: {str(e)}"

    # Check Core DB Replica
    try:
        pool = await get_core_replica_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        health_status["components"]["core_replica"] = "ok"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["core_replica"] = f"error: {str(e)}"

    return health_status
