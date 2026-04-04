"""
Bulk API Router — Third-party data access endpoints.

All queries read from Core DB Replica — zero load on primary.
"""
import time
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, Query

from ..utils.auth import verify_third_party_access, require_scope
from ..services import bulk_service
from ..services.rate_limiter import rate_limiter
from ..database import get_core_primary_pool

logger = logging.getLogger(__name__)


async def apply_rate_limit(request: Request):
    """Rate limit dependency — runs after auth, before endpoint logic."""
    consumer_id = getattr(request.state, "consumer_id", None)
    if not consumer_id:
        return  # Skip if no consumer (shouldn't happen after auth)
    
    result = await rate_limiter.check_rate_limit(consumer_id)
    
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": "Too many requests. Please retry after the specified time.",
                "retry_after": result.retry_after,
                "retry_after_ms": (result.retry_after or 0) * 1000,
            },
        )
    
    # Store result for response headers (set by middleware or endpoint)
    request.state.rate_limit_result = result


router = APIRouter(
    prefix="/api/v1",
    tags=["API"],
    dependencies=[Depends(verify_third_party_access), Depends(apply_rate_limit)],
)


def _get_merchant_id(request: Request) -> int:
    """Extract and validate X-Merchant-ID header."""
    merchant_id = getattr(request.state, "merchant_id", None)
    if merchant_id is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_request", "message": "X-Merchant-ID header is required", "code": "MISSING_HEADER"},
        )
    return merchant_id


async def _log_audit(request: Request, status_code: int, response_time_ms: int):
    """Fire-and-forget audit log insert to Core DB Primary."""
    try:
        pool = await get_core_primary_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO public.api_call_audit_log
                    (consumer_id, merchant_id, endpoint, method, status_code, response_time_ms, request_params)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                request.state.consumer_id,
                getattr(request.state, "merchant_id", None),
                request.url.path,
                request.method,
                status_code,
                response_time_ms,
                dict(request.query_params),
            )
    except Exception:
        pass  # Non-blocking — audit failure should not break the API


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse ISO 8601 datetime string."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": f"Invalid datetime format: {value}"})


# ─── Payments ─────────────────────────────────────────────

@router.get("/payments", dependencies=[Depends(require_scope("payments:read"))])
async def list_payments(
    request: Request,
    cursor: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    status: Optional[str] = None,
    method: Optional[str] = None,
    created_gte: Optional[str] = None,
    created_lte: Optional[str] = None,
    updated_since: Optional[str] = None,
    include_count: bool = False,
):
    """List payments with cursor-based pagination. Reads from Core DB Replica."""
    merchant_id = _get_merchant_id(request)
    start = time.time()

    try:
        result = await bulk_service.get_payments(
            merchant_id=merchant_id,
            cursor=cursor,
            limit=limit,
            status=status,
            method=method,
            created_gte=_parse_datetime(created_gte),
            created_lte=_parse_datetime(created_lte),
            updated_since=_parse_datetime(updated_since),
            include_count=include_count,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": str(e)})

    elapsed_ms = int((time.time() - start) * 1000)
    await _log_audit(request, 200, elapsed_ms)

    return result


# ─── Customers ────────────────────────────────────────────

@router.get("/customers", dependencies=[Depends(require_scope("customers:read"))])
async def list_customers(
    request: Request,
    cursor: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    updated_since: Optional[str] = None,
    include_count: bool = False,
):
    """List customers with cursor-based pagination. Reads from Core DB Replica."""
    merchant_id = _get_merchant_id(request)
    start = time.time()

    try:
        result = await bulk_service.get_customers(
            merchant_id=merchant_id,
            cursor=cursor,
            limit=limit,
            updated_since=_parse_datetime(updated_since),
            include_count=include_count,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": str(e)})

    elapsed_ms = int((time.time() - start) * 1000)
    await _log_audit(request, 200, elapsed_ms)

    return result


# ─── Refunds ──────────────────────────────────────────────

@router.get("/refunds", dependencies=[Depends(require_scope("refunds:read"))])
async def list_refunds(
    request: Request,
    cursor: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    status: Optional[str] = None,
    created_gte: Optional[str] = None,
    created_lte: Optional[str] = None,
    updated_since: Optional[str] = None,
    include_count: bool = False,
):
    """List refunds with cursor-based pagination. Reads from Core DB Replica."""
    merchant_id = _get_merchant_id(request)
    start = time.time()

    try:
        result = await bulk_service.get_refunds(
            merchant_id=merchant_id,
            cursor=cursor,
            limit=limit,
            status=status,
            created_gte=_parse_datetime(created_gte),
            created_lte=_parse_datetime(created_lte),
            updated_since=_parse_datetime(updated_since),
            include_count=include_count,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": str(e)})

    elapsed_ms = int((time.time() - start) * 1000)
    await _log_audit(request, 200, elapsed_ms)

    return result


# ─── Events ───────────────────────────────────────────────

@router.get("/events", dependencies=[Depends(require_scope("events:read"))])
async def list_events(
    request: Request,
    cursor: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    event_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    created_gte: Optional[str] = None,
    created_lte: Optional[str] = None,
    include_count: bool = False,
):
    """List domain events with cursor-based pagination. Reads from Core DB Replica."""
    merchant_id = _get_merchant_id(request)
    start = time.time()

    try:
        result = await bulk_service.get_events(
            merchant_id=merchant_id,
            cursor=cursor,
            limit=limit,
            event_type=event_type,
            entity_type=entity_type,
            created_gte=_parse_datetime(created_gte),
            created_lte=_parse_datetime(created_lte),
            include_count=include_count,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": str(e)})

    elapsed_ms = int((time.time() - start) * 1000)
    await _log_audit(request, 200, elapsed_ms)

    return result


# ─── Merchants ────────────────────────────────────────────

@router.get("/merchants", dependencies=[Depends(require_scope("merchants:read"))])
async def list_merchants(request: Request):
    """List all merchants assigned to this consumer. Reads from Core DB Replica."""
    start = time.time()
    result = await bulk_service.get_assigned_merchants(request.state.consumer_id)
    elapsed_ms = int((time.time() - start) * 1000)
    await _log_audit(request, 200, elapsed_ms)
    return result
