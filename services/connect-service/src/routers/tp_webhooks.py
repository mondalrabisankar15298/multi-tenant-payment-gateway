"""
Third-Party Webhook Management Router.

Consumer-facing endpoints for managing their own webhook subscriptions.
"""
import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel

from ..utils.auth import verify_third_party_access, require_scope
from ..services.tp_webhook_service import (
    create_endpoint,
    get_consumer_endpoints,
    get_endpoint,
    update_endpoint,
    delete_endpoint,
    verify_endpoint as do_verify_endpoint,
    get_delivery_events,
    get_dlq_entries,
)
from ..tasks.tp_webhook_retry_task import tp_dlq_retry

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/third-party/webhooks",
    tags=["Third-Party Webhooks"],
    dependencies=[Depends(verify_third_party_access), Depends(require_scope("webhooks:manage"))],
)


# ─── Request Models ───────────────────────────────────────

class CreateEndpointRequest(BaseModel):
    url: str
    event_types: list[str]
    merchant_id: Optional[int] = None
    metadata: Optional[dict] = None


class UpdateEndpointRequest(BaseModel):
    url: Optional[str] = None
    event_types: Optional[list[str]] = None
    metadata: Optional[dict] = None


# ─── Endpoints ────────────────────────────────────────────

@router.post("", status_code=201)
async def create_webhook_endpoint(request: Request, req: CreateEndpointRequest):
    """Create a webhook endpoint. Triggers ping verification if configured."""
    endpoint = await create_endpoint(
        consumer_id=request.state.consumer_id,
        url=req.url,
        event_types=req.event_types,
        merchant_id=req.merchant_id,
        metadata=req.metadata,
    )
    return {"data": endpoint}


@router.get("")
async def list_webhook_endpoints(request: Request):
    """List all webhook endpoints for this consumer."""
    endpoints = await get_consumer_endpoints(request.state.consumer_id)
    return {"data": endpoints, "total": len(endpoints)}


@router.get("/{endpoint_id}")
async def get_webhook_endpoint(request: Request, endpoint_id: str):
    """Get a specific webhook endpoint."""
    endpoint = await get_endpoint(endpoint_id, request.state.consumer_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return {"data": endpoint}


@router.put("/{endpoint_id}")
async def update_webhook_endpoint(request: Request, endpoint_id: str, req: UpdateEndpointRequest):
    """Update a webhook endpoint."""
    updated = await update_endpoint(endpoint_id, request.state.consumer_id, **req.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return {"data": updated}


@router.delete("/{endpoint_id}")
async def delete_webhook_endpoint(request: Request, endpoint_id: str):
    """Delete a webhook endpoint."""
    deleted = await delete_endpoint(endpoint_id, request.state.consumer_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return {"message": "Endpoint deleted"}


@router.post("/{endpoint_id}/verify")
async def verify_webhook_endpoint(request: Request, endpoint_id: str):
    """Re-trigger ping verification for an endpoint."""
    endpoint = await get_endpoint(endpoint_id, request.state.consumer_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")

    verified = await do_verify_endpoint(endpoint["url"], endpoint["signing_secret"])

    if verified:
        await update_endpoint(endpoint_id, request.state.consumer_id, status="active")
        return {"message": "Endpoint verified successfully", "status": "active"}
    else:
        return {"message": "Endpoint verification failed — ensure your URL responds with 2xx to POST requests", "status": "pending_verification"}


@router.get("/{endpoint_id}/events")
async def list_delivery_events(request: Request, endpoint_id: str, limit: int = 50):
    """Get delivery event log for a specific endpoint."""
    endpoint = await get_endpoint(endpoint_id, request.state.consumer_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")

    events = await get_delivery_events(endpoint_id, limit)
    return {"data": events, "total": len(events)}


# ─── DLQ ──────────────────────────────────────────────────

@router.get("/dlq/entries")
async def list_dlq_entries(request: Request, limit: int = 50):
    """Get DLQ entries for this consumer."""
    entries = await get_dlq_entries(request.state.consumer_id, limit)
    return {"data": entries, "total": len(entries)}


@router.post("/dlq/{dlq_id}/retry")
async def retry_dlq_entry(request: Request, dlq_id: str):
    """Retry a DLQ entry."""
    tp_dlq_retry.delay(dlq_id)
    return {"message": "DLQ entry queued for retry"}
