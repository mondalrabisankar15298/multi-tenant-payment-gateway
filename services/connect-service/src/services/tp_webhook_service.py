"""
Third-Party Webhook Service — Dispatch + Verify + HMAC signing.

Writes to Core DB Primary. Endpoint lookups from Primary for consistency.
"""
import hashlib
import hmac
import json
import time
import logging
import secrets
import random
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import httpx

from ..config import settings
from ..database import get_core_primary_pool

logger = logging.getLogger(__name__)

# ─── Retry Schedule with Jitter ──────────────────────────

RETRY_DELAYS = {
    2: 30,        # 30 seconds
    3: 300,       # 5 minutes
    4: 1800,      # 30 minutes
    5: 7200,      # 2 hours
    6: 86400,     # 24 hours
}


def get_retry_delay(attempt: int) -> int:
    """Exponential backoff with ±20% jitter to prevent thundering herd."""
    base_delay = RETRY_DELAYS.get(attempt, 86400)
    jitter = random.uniform(0.8, 1.2)
    return int(base_delay * jitter)


# ─── HMAC Signing ─────────────────────────────────────────

def sign_payload(signing_secret: str, payload_bytes: bytes) -> str:
    """Sign payload with HMAC-SHA256. Returns 'sha256={hex_digest}'."""
    signature = hmac.new(signing_secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={signature}"


# ─── Event Type Wildcard Matching ─────────────────────────

def matches_event_type(subscribed_types: list[str], event_type: str) -> bool:
    """
    Check if event matches any subscribed pattern.
    Supports: exact match, wildcard (payment.*), and all (*).
    """
    for pattern in subscribed_types:
        if pattern == "*":
            return True
        if pattern == event_type:
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if event_type.startswith(prefix + "."):
                return True
    return False


# ─── Endpoint Verification (Ping) ─────────────────────────

async def verify_endpoint(endpoint_url: str, signing_secret: str) -> bool:
    """
    Send a ping event to verify the endpoint is reachable.
    Returns True if the endpoint responds with 2xx.
    """
    ping_payload = {
        "type": "webhook.endpoint.verification",
        "challenge": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    payload_bytes = json.dumps(ping_payload, sort_keys=True).encode()
    signature = sign_payload(signing_secret, payload_bytes)
    timestamp = str(int(time.time()))

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": "webhook.endpoint.verification",
        "X-Webhook-Signature": signature,
        "X-Webhook-Timestamp": timestamp,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.TP_WEBHOOK_TIMEOUT_SECONDS) as client:
            response = await client.post(endpoint_url, content=payload_bytes, headers=headers)
            return 200 <= response.status_code < 300
    except Exception as e:
        logger.warning(f"Endpoint verification failed for {endpoint_url}: {e}")
        return False


# ─── Endpoint Management ──────────────────────────────────

async def create_endpoint(
    consumer_id: str,
    url: str,
    event_types: list[str],
    merchant_id: int = None,
    metadata: dict = None,
) -> dict:
    """Create a webhook endpoint and optionally verify it."""
    pool = await get_core_primary_pool()
    signing_secret = f"whsec_{secrets.token_urlsafe(32)}"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO public.tp_webhook_endpoints
                (consumer_id, merchant_id, url, event_types, signing_secret, metadata)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            consumer_id, merchant_id, url, event_types, signing_secret, metadata or {},
        )

    endpoint = dict(row)

    # Verify endpoint if configured
    if settings.TP_WEBHOOK_VERIFY_ON_CREATE:
        verified = await verify_endpoint(url, signing_secret)
        if verified:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE public.tp_webhook_endpoints SET status = 'active', updated_at = $2 WHERE endpoint_id = $1",
                    endpoint["endpoint_id"], datetime.now(timezone.utc),
                )
            endpoint["status"] = "active"

    return endpoint


async def get_consumer_endpoints(consumer_id: str) -> list[dict]:
    """Get all webhook endpoints for a consumer."""
    pool = await get_core_primary_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM public.tp_webhook_endpoints WHERE consumer_id = $1 ORDER BY created_at DESC",
            consumer_id,
        )
    return [dict(r) for r in rows]


async def get_endpoint(endpoint_id: str, consumer_id: str = None) -> dict | None:
    """Get a specific endpoint."""
    pool = await get_core_primary_pool()
    query = "SELECT * FROM public.tp_webhook_endpoints WHERE endpoint_id = $1"
    params = [endpoint_id]

    if consumer_id:
        query += " AND consumer_id = $2"
        params.append(consumer_id)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
    return dict(row) if row else None


async def update_endpoint(endpoint_id: str, consumer_id: str, **kwargs) -> dict | None:
    """Update endpoint fields."""
    pool = await get_core_primary_pool()
    allowed = {"url", "event_types", "metadata", "status"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return await get_endpoint(endpoint_id, consumer_id)

    set_clauses = []
    params = []
    idx = 1
    for key, value in updates.items():
        set_clauses.append(f"{key} = ${idx}")
        params.append(value)
        idx += 1

    set_clauses.append(f"updated_at = ${idx}")
    params.append(datetime.now(timezone.utc))
    idx += 1
    params.extend([endpoint_id, consumer_id])

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE public.tp_webhook_endpoints SET {', '.join(set_clauses)} "
            f"WHERE endpoint_id = ${idx} AND consumer_id = ${idx + 1} RETURNING *",
            *params,
        )
    return dict(row) if row else None


async def delete_endpoint(endpoint_id: str, consumer_id: str) -> bool:
    """Delete a webhook endpoint."""
    pool = await get_core_primary_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM public.tp_webhook_endpoints WHERE endpoint_id = $1 AND consumer_id = $2",
            endpoint_id, consumer_id,
        )
    return result != "DELETE 0"


# ─── Webhook Dispatch ─────────────────────────────────────

async def dispatch_webhook(endpoint: dict, event: dict) -> dict:
    """
    Deliver a webhook event to an endpoint.
    Returns delivery log entry.
    """
    pool = await get_core_primary_pool()
    event_delivery_id = uuid4()

    payload = {
        "event_id": str(event.get("event_id", uuid4())),
        "event_type": event.get("event_type"),
        "merchant_id": event.get("merchant_id"),
        "data": event.get("payload", event.get("data", {})),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode()
    signature = sign_payload(endpoint["signing_secret"], payload_bytes)
    timestamp = str(int(time.time()))

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Id": str(event_delivery_id),
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
                delivery_status = "failed"  # Client error — don't retry, disable endpoint
            else:
                delivery_status = "failed"  # Server error — will retry

    except Exception as e:
        delivery_status = "failed"
        response_body = str(e)[:500]

    # Log delivery event to Core DB Primary
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO public.tp_webhook_events
                (event_delivery_id, endpoint_id, consumer_id, event_id, event_type,
                 merchant_id, payload, status, attempts, last_status_code, last_response)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 1, $9, $10)
            """,
            event_delivery_id,
            endpoint["endpoint_id"],
            endpoint["consumer_id"],
            str(event.get("event_id", str(uuid4()))),
            event.get("event_type", "unknown"),
            event.get("merchant_id", 0),
            payload,
            delivery_status,
            status_code,
            response_body,
        )

    return {
        "event_delivery_id": str(event_delivery_id),
        "status": delivery_status,
        "status_code": status_code,
        "response_body": response_body,
    }


async def get_active_endpoints_for_event(event_type: str, merchant_id: int) -> list[dict]:
    """Find all active webhook endpoints matching this event type and merchant.
    Only returns endpoints belonging to active consumers."""
    pool = await get_core_primary_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT e.*
            FROM public.tp_webhook_endpoints e
            JOIN public.third_party_consumers c ON c.consumer_id = e.consumer_id
            WHERE e.status = 'active'
              AND c.status = 'active'
              AND (e.merchant_id IS NULL OR e.merchant_id = $1)
            """,
            merchant_id,
        )

    # Filter by event type pattern matching
    matching = []
    for row in rows:
        endpoint = dict(row)
        if matches_event_type(endpoint["event_types"], event_type):
            matching.append(endpoint)

    return matching


# ─── DLQ ──────────────────────────────────────────────────

async def move_to_dlq(event_delivery_id: str, failure_reason: str):
    """Move a failed delivery to the dead letter queue."""
    pool = await get_core_primary_pool()
    async with pool.acquire() as conn:
        event = await conn.fetchrow(
            "SELECT * FROM public.tp_webhook_events WHERE event_delivery_id = $1",
            event_delivery_id,
        )
        if not event:
            return

        await conn.execute(
            """
            INSERT INTO public.tp_dead_letter_queue
                (endpoint_id, consumer_id, event_id, merchant_id, payload, failure_reason, max_attempts)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            event["endpoint_id"], event["consumer_id"], event["event_id"],
            event["merchant_id"], event["payload"], failure_reason, event["attempts"],
        )

        await conn.execute(
            "UPDATE public.tp_webhook_events SET status = 'dlq', updated_at = $2 WHERE event_delivery_id = $1",
            event_delivery_id, datetime.now(timezone.utc),
        )


async def get_dlq_entries(consumer_id: str = None, limit: int = 50) -> list[dict]:
    """Get DLQ entries, optionally filtered by consumer."""
    pool = await get_core_primary_pool()
    if consumer_id:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM public.tp_dead_letter_queue WHERE consumer_id = $1 ORDER BY created_at DESC LIMIT $2",
                consumer_id, limit,
            )
    else:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM public.tp_dead_letter_queue ORDER BY created_at DESC LIMIT $1",
                limit,
            )
    return [dict(r) for r in rows]


async def get_delivery_events(endpoint_id: str, limit: int = 50) -> list[dict]:
    """Get delivery event log for an endpoint."""
    pool = await get_core_primary_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM public.tp_webhook_events WHERE endpoint_id = $1 ORDER BY created_at DESC LIMIT $2",
            endpoint_id, limit,
        )
    return [dict(r) for r in rows]
