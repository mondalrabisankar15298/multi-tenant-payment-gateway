"""
Bulk Service — Queries Core DB Read Replica for third-party data access.

All read queries run against the replica — zero load on primary.
"""
import time
import logging
from datetime import datetime

from ..database import get_core_replica_pool
from ..utils.cursor import encode_cursor, decode_cursor
from ..utils.validators import validate_schema_name

logger = logging.getLogger(__name__)

# ─── Schema resolution cache ─────────────────────────────

_schema_cache: dict[int, tuple[str, float]] = {}
_SCHEMA_CACHE_TTL = 300  # 5 minutes


async def resolve_merchant_schema(merchant_id: int) -> str:
    """Resolve merchant_id → schema_name using the replica. Cached for 5 min."""
    now = time.time()
    if merchant_id in _schema_cache:
        schema, expires_at = _schema_cache[merchant_id]
        if now < expires_at:
            return schema

    pool = await get_core_replica_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT schema_name FROM public.merchants WHERE merchant_id = $1 AND status = 'active'",
            merchant_id,
        )

    if not row:
        raise ValueError(f"Merchant {merchant_id} not found or inactive")

    schema = validate_schema_name(row["schema_name"])
    _schema_cache[merchant_id] = (schema, now + _SCHEMA_CACHE_TTL)
    return schema


# ─── Bulk Query Results ───────────────────────────────────

def _build_bulk_response(rows: list[dict], limit: int, cursor_field: str, id_field: str, merchant_id: int = None, total_count: int = None) -> dict:
    """Build standardized bulk API response with cursor pagination."""
    has_more = len(rows) > limit
    data = rows[:limit]  # Trim the extra row used for has_more detection

    next_cursor = None
    if has_more and data:
        last = data[-1]
        next_cursor = encode_cursor(last[cursor_field], str(last[id_field]))

    response = {
        "object": "list",
        "data": data,
        "pagination": {
            "next_cursor": next_cursor,
            "has_more": has_more,
            "limit": limit,
        },
    }

    metadata = {}
    if merchant_id:
        metadata["merchant_id"] = merchant_id
    if total_count is not None:
        metadata["total_count"] = total_count
    if metadata:
        response["metadata"] = metadata

    return response


def _serialize_row(row: dict) -> dict:
    """Convert asyncpg Row values for JSON serialization."""
    result = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif hasattr(value, "__str__") and not isinstance(value, (str, int, float, bool, list, dict, type(None))):
            result[key] = str(value)
        else:
            result[key] = value
    return result


# ─── Payments ─────────────────────────────────────────────

async def get_payments(
    merchant_id: int,
    cursor: str = None,
    limit: int = 100,
    status: str = None,
    method: str = None,
    created_gte: datetime = None,
    created_lte: datetime = None,
    updated_since: datetime = None,
    include_count: bool = False,
) -> dict:
    """Query payments from replica with cursor pagination."""
    schema = await resolve_merchant_schema(merchant_id)
    pool = await get_core_replica_pool()

    conditions = []
    params = []
    idx = 1

    if cursor:
        cursor_time, cursor_id = decode_cursor(cursor)
        conditions.append(f"(p.updated_at, p.payment_id) > (${idx}, ${idx + 1})")
        params.extend([cursor_time, cursor_id])
        idx += 2

    if status:
        conditions.append(f"p.status = ${idx}")
        params.append(status)
        idx += 1

    if method:
        conditions.append(f"p.method = ${idx}")
        params.append(method)
        idx += 1

    if created_gte:
        conditions.append(f"p.created_at >= ${idx}")
        params.append(created_gte)
        idx += 1

    if created_lte:
        conditions.append(f"p.created_at <= ${idx}")
        params.append(created_lte)
        idx += 1

    if updated_since:
        conditions.append(f"p.updated_at > ${idx}")
        params.append(updated_since)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT p.payment_id, c.customer_id, p.amount, p.currency, p.status, p.method,
               p.description, p.metadata, p.failure_reason, p.amount_refunded,
               p.created_at, p.updated_at
        FROM {schema}.payments p
        JOIN {schema}.customers c ON c.id = p.customer_ref
        {where}
        ORDER BY p.updated_at ASC, p.payment_id ASC
        LIMIT ${idx}
    """
    params.append(limit + 1)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

        total_count = None
        if include_count:
            count_query = f"SELECT COUNT(*) FROM {schema}.payments p {where}"
            total_count = await conn.fetchval(count_query, *params[:-1])

    serialized = [_serialize_row(dict(r)) for r in rows]
    return _build_bulk_response(serialized, limit, "updated_at", "payment_id", merchant_id, total_count)


# ─── Customers ────────────────────────────────────────────

async def get_customers(
    merchant_id: int,
    cursor: str = None,
    limit: int = 100,
    updated_since: datetime = None,
    include_count: bool = False,
) -> dict:
    """Query customers from replica with cursor pagination."""
    schema = await resolve_merchant_schema(merchant_id)
    pool = await get_core_replica_pool()

    conditions = []
    params = []
    idx = 1

    if cursor:
        cursor_time, cursor_id = decode_cursor(cursor)
        conditions.append(f"(updated_at, customer_id) > (${idx}, ${idx + 1})")
        params.extend([cursor_time, cursor_id])
        idx += 2

    if updated_since:
        conditions.append(f"updated_at > ${idx}")
        params.append(updated_since)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT customer_id, name, email, phone, created_at, updated_at
        FROM {schema}.customers
        {where}
        ORDER BY updated_at ASC, customer_id ASC
        LIMIT ${idx}
    """
    params.append(limit + 1)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

        total_count = None
        if include_count:
            count_query = f"SELECT COUNT(*) FROM {schema}.customers {where}"
            total_count = await conn.fetchval(count_query, *params[:-1])

    serialized = [_serialize_row(dict(r)) for r in rows]
    return _build_bulk_response(serialized, limit, "updated_at", "customer_id", merchant_id, total_count)


# ─── Refunds ──────────────────────────────────────────────

async def get_refunds(
    merchant_id: int,
    cursor: str = None,
    limit: int = 100,
    status: str = None,
    created_gte: datetime = None,
    created_lte: datetime = None,
    updated_since: datetime = None,
    include_count: bool = False,
) -> dict:
    """Query refunds from replica with cursor pagination."""
    schema = await resolve_merchant_schema(merchant_id)
    pool = await get_core_replica_pool()

    conditions = []
    params = []
    idx = 1

    if cursor:
        cursor_time, cursor_id = decode_cursor(cursor)
        conditions.append(f"(r.updated_at, r.refund_id) > (${idx}, ${idx + 1})")
        params.extend([cursor_time, cursor_id])
        idx += 2

    if status:
        conditions.append(f"r.status = ${idx}")
        params.append(status)
        idx += 1

    if created_gte:
        conditions.append(f"r.created_at >= ${idx}")
        params.append(created_gte)
        idx += 1

    if created_lte:
        conditions.append(f"r.created_at <= ${idx}")
        params.append(created_lte)
        idx += 1

    if updated_since:
        conditions.append(f"r.updated_at > ${idx}")
        params.append(updated_since)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT r.refund_id, p.payment_id, r.amount, r.reason, r.status,
               r.created_at, r.updated_at
        FROM {schema}.refunds r
        JOIN {schema}.payments p ON p.id = r.payment_ref
        {where}
        ORDER BY r.updated_at ASC, r.refund_id ASC
        LIMIT ${idx}
    """
    params.append(limit + 1)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

        total_count = None
        if include_count:
            count_query = f"SELECT COUNT(*) FROM {schema}.refunds r {where}"
            total_count = await conn.fetchval(count_query, *params[:-1])

    serialized = [_serialize_row(dict(r)) for r in rows]
    return _build_bulk_response(serialized, limit, "updated_at", "refund_id", merchant_id, total_count)


# ─── Domain Events ────────────────────────────────────────

async def get_events(
    merchant_id: int,
    cursor: str = None,
    limit: int = 100,
    event_type: str = None,
    entity_type: str = None,
    created_gte: datetime = None,
    created_lte: datetime = None,
    include_count: bool = False,
) -> dict:
    """Query domain events from replica with cursor pagination."""
    pool = await get_core_replica_pool()

    conditions = [f"merchant_id = ${1}"]
    params = [merchant_id]
    idx = 2

    if cursor:
        cursor_time, cursor_id = decode_cursor(cursor)
        conditions.append(f"(created_at, event_id) > (${idx}, ${idx + 1})")
        params.extend([cursor_time, cursor_id])
        idx += 2

    if event_type:
        conditions.append(f"event_type = ${idx}")
        params.append(event_type)
        idx += 1

    if entity_type:
        conditions.append(f"entity_type = ${idx}")
        params.append(entity_type)
        idx += 1

    if created_gte:
        conditions.append(f"created_at >= ${idx}")
        params.append(created_gte)
        idx += 1

    if created_lte:
        conditions.append(f"created_at <= ${idx}")
        params.append(created_lte)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}"

    query = f"""
        SELECT event_id, merchant_id, event_type, entity_type, entity_id,
               payload, status, created_at
        FROM public.domain_events
        {where}
        ORDER BY created_at ASC, event_id ASC
        LIMIT ${idx}
    """
    params.append(limit + 1)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

        total_count = None
        if include_count:
            count_query = f"SELECT COUNT(*) FROM public.domain_events {where}"
            total_count = await conn.fetchval(count_query, *params[:-1])

    serialized = [_serialize_row(dict(r)) for r in rows]
    return _build_bulk_response(serialized, limit, "created_at", "event_id", merchant_id, total_count)


# ─── Assigned Merchants ──────────────────────────────────

async def get_assigned_merchants(consumer_id: str) -> dict:
    """Get all merchants assigned to a consumer from replica."""
    pool = await get_core_replica_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT m.merchant_id, m.name, m.email, m.status, m.created_at,
                   cma.granted_at, cma.scopes
            FROM public.consumer_merchant_access cma
            JOIN public.merchants m ON m.merchant_id = cma.merchant_id
            WHERE cma.consumer_id = $1
            ORDER BY m.name ASC
            """,
            consumer_id,
        )

    data = [_serialize_row(dict(r)) for r in rows]
    return {"object": "list", "data": data, "pagination": {"has_more": False}, "metadata": {"total_count": len(data)}}
