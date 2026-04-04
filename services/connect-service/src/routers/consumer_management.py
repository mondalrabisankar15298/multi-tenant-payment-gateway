"""
Consumer Management API — Admin-only endpoints.

All endpoints require X-Admin-Key header.
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel

from ..utils.auth import verify_admin_access
from ..services.oauth_service import (
    register_consumer,
    get_consumer,
    list_consumers,
    update_consumer,
    suspend_consumer,
    revoke_consumer,
    rotate_secret,
    assign_merchants,
    remove_merchant_access,
    get_consumer_merchants,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/admin/consumers",
    tags=["Admin - Consumers"],
    dependencies=[Depends(verify_admin_access)],
)


# ─── Request/Response Models ──────────────────────────────

class CreateConsumerRequest(BaseModel):
    name: str
    description: Optional[str] = None
    scopes: list[str] = ["payments:read", "customers:read"]
    rate_limit_requests: Optional[int] = None
    rate_limit_window_seconds: Optional[int] = None


class UpdateConsumerRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scopes: Optional[list[str]] = None
    status: Optional[str] = None
    webhook_url: Optional[str] = None
    webhook_event_types: Optional[list[str]] = None
    rate_limit_requests: Optional[int] = None
    rate_limit_window_seconds: Optional[int] = None
    metadata: Optional[dict] = None


class AssignMerchantsRequest(BaseModel):
    merchant_ids: list[int]


# ─── Endpoints ────────────────────────────────────────────

@router.post("", status_code=201)
async def create_consumer(req: CreateConsumerRequest):
    """Register a new third-party consumer. Returns client_secret ONCE."""
    consumer = await register_consumer(
        name=req.name,
        description=req.description,
        scopes=req.scopes,
        rate_limit_requests=req.rate_limit_requests,
        rate_limit_window_seconds=req.rate_limit_window_seconds,
    )
    return {"data": consumer}


@router.get("")
async def list_all_consumers():
    """List all registered third-party consumers."""
    consumers = await list_consumers()
    return {"data": consumers, "total": len(consumers)}


@router.get("/{consumer_id}")
async def get_consumer_detail(consumer_id: str):
    """Get a specific consumer with assigned merchants."""
    consumer = await get_consumer(consumer_id)
    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    merchants = await get_consumer_merchants(consumer_id)
    return {"data": {**consumer, "merchants": merchants}}


@router.put("/{consumer_id}")
async def update_consumer_endpoint(consumer_id: str, req: UpdateConsumerRequest):
    """Update consumer details."""
    updated = await update_consumer(consumer_id, **req.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Consumer not found")
    return {"data": updated}


@router.delete("/{consumer_id}")
async def delete_consumer(consumer_id: str):
    """Revoke a consumer permanently."""
    result = await revoke_consumer(consumer_id)
    if not result:
        raise HTTPException(status_code=404, detail="Consumer not found")
    return {"data": result, "message": "Consumer revoked"}


@router.post("/{consumer_id}/rotate-secret")
async def rotate_consumer_secret(consumer_id: str):
    """Rotate client secret. Returns new secret ONCE."""
    result = await rotate_secret(consumer_id)
    if not result:
        raise HTTPException(status_code=404, detail="Consumer not found")
    return {"data": result, "message": "Secret rotated successfully. Save the new client_secret — it won't be shown again."}


@router.post("/{consumer_id}/suspend")
async def suspend_consumer_endpoint(consumer_id: str):
    """Suspend a consumer (can be reactivated)."""
    result = await suspend_consumer(consumer_id)
    if not result:
        raise HTTPException(status_code=404, detail="Consumer not found")
    return {"data": result, "message": "Consumer suspended"}


@router.post("/{consumer_id}/activate")
async def activate_consumer_endpoint(consumer_id: str):
    """Reactivate a suspended consumer."""
    result = await update_consumer(consumer_id, status="active")
    if not result:
        raise HTTPException(status_code=404, detail="Consumer not found")
    return {"data": result, "message": "Consumer activated"}


# ─── Merchant Assignment ──────────────────────────────────

@router.post("/{consumer_id}/merchants")
async def assign_merchants_endpoint(consumer_id: str, req: AssignMerchantsRequest):
    """Assign merchants to a consumer."""
    consumer = await get_consumer(consumer_id)
    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    results = await assign_merchants(consumer_id, req.merchant_ids)
    return {"data": results, "message": f"Assigned {len(results)} merchants"}


@router.delete("/{consumer_id}/merchants/{merchant_id}")
async def remove_merchant_endpoint(consumer_id: str, merchant_id: int):
    """Remove merchant access from a consumer."""
    removed = await remove_merchant_access(consumer_id, merchant_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Merchant access not found")
    return {"message": "Merchant access removed"}


@router.get("/{consumer_id}/merchants")
async def list_consumer_merchants(consumer_id: str):
    """List all merchants assigned to a consumer."""
    consumer = await get_consumer(consumer_id)
    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    merchants = await get_consumer_merchants(consumer_id)
    return {"data": merchants, "total": len(merchants)}
