"""
Analytics API Router — Admin-only endpoints.
All queries read from Core DB Replica.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..utils.auth import verify_admin_access
from ..services.analytics_service import (
    get_system_overview,
    get_consumer_stats,
    get_time_series_api_calls,
    get_time_series_webhooks,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/admin/analytics",
    tags=["Admin - Analytics"],
    dependencies=[Depends(verify_admin_access)],
)


@router.get("/overview")
async def analytics_overview():
    """System-wide analytics overview."""
    data = await get_system_overview()
    return {"data": data}


@router.get("/consumers/{consumer_id}")
async def consumer_analytics(consumer_id: str):
    """Detailed analytics for a specific consumer."""
    data = await get_consumer_stats(consumer_id)
    return {"data": data}


@router.get("/consumers/{consumer_id}/api-calls")
async def consumer_api_calls_timeseries(
    consumer_id: str,
    from_dt: Optional[str] = Query(None, alias="from"),
    to_dt: Optional[str] = Query(None, alias="to"),
    granularity: str = "hour",
):
    """Time-series API call data for a consumer."""
    now = datetime.now(timezone.utc)
    from_datetime = datetime.fromisoformat(from_dt) if from_dt else now - timedelta(hours=24)
    to_datetime = datetime.fromisoformat(to_dt) if to_dt else now

    data = await get_time_series_api_calls(consumer_id, from_datetime, to_datetime, granularity)
    return {"data": data, "granularity": granularity}


@router.get("/consumers/{consumer_id}/webhooks")
async def consumer_webhooks_timeseries(
    consumer_id: str,
    from_dt: Optional[str] = Query(None, alias="from"),
    to_dt: Optional[str] = Query(None, alias="to"),
    granularity: str = "hour",
):
    """Time-series webhook delivery data for a consumer."""
    now = datetime.now(timezone.utc)
    from_datetime = datetime.fromisoformat(from_dt) if from_dt else now - timedelta(hours=24)
    to_datetime = datetime.fromisoformat(to_dt) if to_dt else now

    data = await get_time_series_webhooks(consumer_id, from_datetime, to_datetime, granularity)
    return {"data": data, "granularity": granularity}
