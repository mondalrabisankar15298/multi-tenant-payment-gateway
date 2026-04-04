"""
Third-Party Webhook Retry Task — Celery-based exponential backoff with jitter.

IMPORTANT: This task updates the EXISTING tp_webhook_events row (increments attempts),
it does NOT create new rows. dispatch_webhook() always creates new rows, so for retries
we do the HTTP dispatch directly and update the original row.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import httpx

from ..celery_app import celery_app
from ..services.tp_webhook_service import (
    get_retry_delay,
    move_to_dlq,
    sign_payload,
)
from ..database import get_core_primary_pool
from ..config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=None, name="tp_webhook_retry")
def tp_webhook_retry(self, event_delivery_id: str):
    """Retry a failed webhook delivery with exponential backoff + jitter."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_retry_delivery(self, event_delivery_id))
    finally:
        loop.close()


async def _do_direct_dispatch(endpoint: dict, event: dict) -> dict:
    """Direct HTTP dispatch for retry — does NOT create a new tp_webhook_events row."""
    payload = {
        "event_id": str(event.get("event_id", str(uuid4()))),
        "event_type": event.get("event_type"),
        "merchant_id": event.get("merchant_id"),
        "data": event.get("data", event.get("payload", {})),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode()
    signature = sign_payload(endpoint["signing_secret"], payload_bytes)
    timestamp = str(int(time.time()))

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Id": str(event.get("event_delivery_id", str(uuid4()))),
        "X-Webhook-Event": event.get("event_type", ""),
        "X-Webhook-Signature": signature,
        "X-Webhook-Timestamp": timestamp,
        "X-Consumer-Id": str(endpoint["consumer_id"]),
        "X-Merchant-Id": str(event.get("merchant_id", "")),
    }

    status_code = None
    response_body = None
    delivery_status = "pending"

    try:
        async with httpx.AsyncClient(timeout=settings.TP_WEBHOOK_TIMEOUT_SECONDS) as client:
            response = await client.post(endpoint["url"], content=payload_bytes, headers=headers)
            status_code = response.status_code
            response_body = response.text[:500]

            if 200 <= status_code < 300:
                delivery_status = "delivered"
            elif 400 <= status_code < 500:
                delivery_status = "failed"
            else:
                delivery_status = "failed"

    except Exception as e:
        delivery_status = "failed"
        response_body = str(e)[:500]

    return {
        "status": delivery_status,
        "status_code": status_code,
        "response_body": response_body,
    }


async def _retry_delivery(task, event_delivery_id: str):
    """Async retry logic — updates the EXISTING row, does not create new ones."""
    pool = await get_core_primary_pool()

    async with pool.acquire() as conn:
        event = await conn.fetchrow(
            "SELECT * FROM public.tp_webhook_events WHERE event_delivery_id = $1",
            event_delivery_id,
        )

    if not event:
        logger.warning(f"Delivery event {event_delivery_id} not found, skipping retry")
        return

    attempt = event["attempts"] + 1

    # Check if max retries exceeded
    if attempt > settings.TP_WEBHOOK_MAX_RETRIES:
        logger.warning(f"Max retries ({settings.TP_WEBHOOK_MAX_RETRIES}) exceeded for {event_delivery_id}, moving to DLQ")
        await move_to_dlq(event_delivery_id, f"Max retries exceeded after {event['attempts']} attempts")
        return

    # Get endpoint for delivery
    async with pool.acquire() as conn:
        endpoint = await conn.fetchrow(
            "SELECT * FROM public.tp_webhook_endpoints WHERE endpoint_id = $1",
            event["endpoint_id"],
        )

    if not endpoint or endpoint["status"] != "active":
        logger.warning(f"Endpoint {event['endpoint_id']} not active, moving to DLQ")
        await move_to_dlq(event_delivery_id, "Endpoint disabled or deleted")
        return

    # Build event data from stored payload
    event_data = {
        "event_id": str(event["event_id"]),
        "event_type": event["event_type"],
        "merchant_id": event["merchant_id"],
        "payload": event["payload"],
        "data": event["payload"],
    }

    # Direct HTTP dispatch (no new row creation)
    endpoint_dict = dict(endpoint)
    result = await _do_direct_dispatch(endpoint_dict, event_data)

    if result["status"] == "delivered":
        # Update the original event record as delivered
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE public.tp_webhook_events
                SET status = 'delivered', attempts = $2, last_status_code = $3,
                    last_response = $4, updated_at = $5
                WHERE event_delivery_id = $1
                """,
                event_delivery_id, attempt, result.get("status_code"),
                result.get("response_body", ""), datetime.now(timezone.utc),
            )
        logger.info(f"Retry successful for {event_delivery_id} on attempt {attempt}")
    else:
        # Schedule next retry
        delay = get_retry_delay(attempt + 1)
        next_retry = datetime.now(timezone.utc) + timedelta(seconds=delay)

        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE public.tp_webhook_events
                SET attempts = $2, last_status_code = $3, last_response = $4,
                    next_retry_at = $5, updated_at = $6
                WHERE event_delivery_id = $1
                """,
                event_delivery_id, attempt, result.get("status_code"),
                str(result.get("response_body", "")), next_retry, datetime.now(timezone.utc),
            )

        logger.info(f"Retry {attempt} failed for {event_delivery_id}, next retry in {delay}s")
        task.apply_async(args=[event_delivery_id], countdown=delay)


@celery_app.task(name="tp_dlq_retry")
def tp_dlq_retry(dlq_id: str):
    """Retry a DLQ entry by re-dispatching."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_dlq_retry(dlq_id))
    finally:
        loop.close()


async def _dlq_retry(dlq_id: str):
    """Async DLQ retry logic."""
    pool = await get_core_primary_pool()

    async with pool.acquire() as conn:
        dlq_entry = await conn.fetchrow(
            "SELECT * FROM public.tp_dead_letter_queue WHERE dlq_id = $1", dlq_id
        )

    if not dlq_entry:
        return

    async with pool.acquire() as conn:
        endpoint = await conn.fetchrow(
            "SELECT * FROM public.tp_webhook_endpoints WHERE endpoint_id = $1",
            dlq_entry["endpoint_id"],
        )

    if not endpoint or endpoint["status"] != "active":
        logger.warning(f"Cannot retry DLQ {dlq_id}: endpoint not active")
        return

    # Build event data — payload is JSONB, access safely
    payload_data = dlq_entry["payload"]
    if isinstance(payload_data, str):
        import json
        try:
            payload_data = json.loads(payload_data)
        except json.JSONDecodeError:
            payload_data = {}

    event_data = {
        "event_id": str(dlq_entry["event_id"]),
        "event_type": payload_data.get("event_type", "unknown"),
        "merchant_id": dlq_entry["merchant_id"],
        "payload": payload_data,
        "data": payload_data.get("data", payload_data),
    }

    result = await _do_direct_dispatch(dict(endpoint), event_data)

    if result["status"] == "delivered":
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM public.tp_dead_letter_queue WHERE dlq_id = $1", dlq_id)
        logger.info(f"DLQ retry successful for {dlq_id}")
    else:
        logger.warning(f"DLQ retry failed for {dlq_id}: {result}")
