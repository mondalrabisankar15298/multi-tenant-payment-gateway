from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request
import logging

from .database import get_pool, close_pool
from .routers import merchants, customers, payments, refunds
from .utils.logger import setup_logging, get_logger
from prometheus_client import make_asgi_app

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create DB pool
    await get_pool()
    yield
    # Shutdown: close DB pool
    await close_pool()


app = FastAPI(
    title="Payment Core Service",
    description="System 1 — Multi-Tenant Payment Gateway (Write Side)",
    version="1.0.0",
    lifespan=lifespan,
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

from .config import settings

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Routers
app.include_router(merchants.router)
app.include_router(customers.router)
app.include_router(payments.router)
app.include_router(refunds.router)


# Events log endpoint
@app.get("/api/events", tags=["events"])
async def get_events(
    status: str = None,
    merchant_id: int = None,
    entity_type: str = None,
    event_type: str = None,
    from_date: str = None,
    to_date: str = None,
    limit: int = 100,
):
    """View domain_events outbox with full filter support (admin portal)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions = []
        params = []
        idx = 1

        if status:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        if merchant_id:
            conditions.append(f"merchant_id = ${idx}")
            params.append(merchant_id)
            idx += 1
        if entity_type:
            conditions.append(f"entity_type = ${idx}")
            params.append(entity_type)
            idx += 1
        if event_type:
            conditions.append(f"event_type = ${idx}")
            params.append(event_type)
            idx += 1
        if from_date:
            conditions.append(f"created_at >= ${idx}::timestamptz")
            params.append(from_date)
            idx += 1
        if to_date:
            conditions.append(f"created_at <= ${idx}::timestamptz + interval '1 day'")
            params.append(to_date)
            idx += 1

        where = " AND ".join(conditions) if conditions else "TRUE"
        params.append(limit)

        rows = await conn.fetch(
            f"SELECT * FROM public.domain_events WHERE {where} ORDER BY created_at DESC LIMIT ${idx}",
            *params,
        )
        return [dict(r) for r in rows]


@app.get("/health", tags=["health"])
async def health_check():
    health_status = {"status": "healthy", "service": "payment-core-service", "components": {}}
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
            health_status["components"]["db"] = "ok"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["components"]["db"] = f"error: {str(e)}"
    
    return health_status
