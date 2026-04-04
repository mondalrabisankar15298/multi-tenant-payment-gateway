"""
OAuth 2.0 + Consumer Management Service

All operations target Core DB Primary (source of truth).
Consumer status is cached in Redis for 60s to avoid per-request DB hits.
"""
import json
import secrets
import logging
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from jose import jwt, JWTError
import bcrypt

from ..config import settings
from ..database import get_core_primary_pool

logger = logging.getLogger(__name__)

# ─── Redis integration (lazy import to avoid circular) ─────

_redis_client = None


async def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


CONSUMER_CACHE_TTL = 60  # seconds


# ─── Consumer CRUD ────────────────────────────────────────

async def register_consumer(
    name: str,
    description: str = None,
    scopes: list[str] = None,
    rate_limit_requests: int = None,
    rate_limit_window_seconds: int = None,
    created_by: str = "admin",
) -> dict:
    """Register a new third-party consumer. Returns consumer with plaintext secret (shown once)."""
    pool = await get_core_primary_pool()

    # Generate credentials
    client_secret = secrets.token_urlsafe(48)
    client_secret_hash = bcrypt.hashpw(client_secret.encode(), bcrypt.gensalt()).decode()
    webhook_signing_secret = f"whsec_{secrets.token_urlsafe(32)}"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO public.third_party_consumers
                (name, description, client_secret_hash, scopes, webhook_signing_secret,
                 rate_limit_requests, rate_limit_window_seconds, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            name,
            description,
            client_secret_hash,
            scopes or [],
            webhook_signing_secret,
            rate_limit_requests or settings.RATE_LIMIT_DEFAULT_REQUESTS,
            rate_limit_window_seconds or settings.RATE_LIMIT_DEFAULT_WINDOW_SECONDS,
            created_by,
        )

    consumer = dict(row)
    # Return plaintext secret only on creation — never stored
    consumer["client_secret"] = client_secret
    consumer.pop("client_secret_hash", None)
    logger.info(f"Registered consumer: {name} ({consumer['consumer_id']})")
    return consumer


async def get_consumer(consumer_id: str) -> dict | None:
    """Get consumer by ID from Core DB Primary."""
    pool = await get_core_primary_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM public.third_party_consumers WHERE consumer_id = $1",
            consumer_id,
        )
    if row:
        consumer = dict(row)
        consumer.pop("client_secret_hash", None)
        return consumer
    return None


async def get_cached_consumer(consumer_id: str) -> dict | None:
    """Get consumer with Redis caching (60s TTL). Falls back to Primary."""
    redis = await _get_redis()
    cache_key = f"consumer:{consumer_id}"

    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    consumer = await get_consumer(consumer_id)
    if consumer:
        await redis.set(cache_key, json.dumps(consumer, default=str), ex=CONSUMER_CACHE_TTL)
    return consumer


async def invalidate_consumer_cache(consumer_id: str):
    """Force re-fetch from DB on next access."""
    redis = await _get_redis()
    await redis.delete(f"consumer:{consumer_id}")


async def list_consumers() -> list[dict]:
    """List all consumers."""
    pool = await get_core_primary_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM public.third_party_consumers ORDER BY created_at DESC"
        )
    result = []
    for row in rows:
        consumer = dict(row)
        consumer.pop("client_secret_hash", None)
        result.append(consumer)
    return result


async def update_consumer(consumer_id: str, **kwargs) -> dict | None:
    """Update consumer fields. Invalidates cache."""
    pool = await get_core_primary_pool()

    allowed_fields = {
        "name", "description", "scopes", "status", "webhook_url",
        "webhook_event_types", "webhook_signing_secret",
        "rate_limit_requests", "rate_limit_window_seconds", "metadata",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return await get_consumer(consumer_id)

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

    params.append(consumer_id)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE public.third_party_consumers SET {', '.join(set_clauses)} "
            f"WHERE consumer_id = ${idx} RETURNING *",
            *params,
        )

    if row:
        await invalidate_consumer_cache(consumer_id)
        consumer = dict(row)
        consumer.pop("client_secret_hash", None)
        return consumer
    return None


async def suspend_consumer(consumer_id: str) -> dict | None:
    """Suspend a consumer. Invalidates cache immediately."""
    return await update_consumer(consumer_id, status="suspended")


async def revoke_consumer(consumer_id: str) -> dict | None:
    """Revoke a consumer permanently. Invalidates cache."""
    return await update_consumer(consumer_id, status="revoked")


async def rotate_secret(consumer_id: str) -> dict | None:
    """Generate new client_secret. Returns plaintext secret once."""
    pool = await get_core_primary_pool()
    new_secret = secrets.token_urlsafe(48)
    new_hash = bcrypt.hashpw(new_secret.encode(), bcrypt.gensalt()).decode()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE public.third_party_consumers
            SET client_secret_hash = $1, updated_at = $2
            WHERE consumer_id = $3 RETURNING *
            """,
            new_hash, datetime.now(timezone.utc), consumer_id,
        )

    if row:
        await invalidate_consumer_cache(consumer_id)
        consumer = dict(row)
        consumer.pop("client_secret_hash", None)
        consumer["client_secret"] = new_secret
        return consumer
    return None


# ─── Merchant Access ──────────────────────────────────────

async def assign_merchants(consumer_id: str, merchant_ids: list[int], granted_by: str = "admin") -> list[dict]:
    """Assign merchants to a consumer."""
    pool = await get_core_primary_pool()
    results = []
    async with pool.acquire() as conn:
        for mid in merchant_ids:
            row = await conn.fetchrow(
                """
                INSERT INTO public.consumer_merchant_access (consumer_id, merchant_id, granted_by)
                VALUES ($1, $2, $3)
                ON CONFLICT (consumer_id, merchant_id) DO NOTHING
                RETURNING *
                """,
                consumer_id, mid, granted_by,
            )
            if row:
                results.append(dict(row))
    return results


async def remove_merchant_access(consumer_id: str, merchant_id: int) -> bool:
    """Remove a merchant from a consumer's access list."""
    pool = await get_core_primary_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM public.consumer_merchant_access WHERE consumer_id = $1 AND merchant_id = $2",
            consumer_id, merchant_id,
        )
    return result != "DELETE 0"


async def get_consumer_merchants(consumer_id: str) -> list[dict]:
    """Get all merchants assigned to a consumer."""
    pool = await get_core_primary_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cma.*, m.name AS merchant_name, m.email AS merchant_email, m.status AS merchant_status
            FROM public.consumer_merchant_access cma
            JOIN public.merchants m ON cma.merchant_id = m.merchant_id
            WHERE cma.consumer_id = $1
            ORDER BY cma.granted_at DESC
            """,
            consumer_id,
        )
    return [dict(r) for r in rows]


async def check_merchant_access(consumer_id: str, merchant_id: int) -> bool:
    """Check if a consumer has access to a specific merchant."""
    pool = await get_core_primary_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM public.consumer_merchant_access WHERE consumer_id = $1 AND merchant_id = $2",
            consumer_id, merchant_id,
        )
    return row is not None


# ─── OAuth Token ──────────────────────────────────────────

async def authenticate_consumer(client_id: str, client_secret: str, requested_scope: str = None) -> dict:
    """
    OAuth 2.0 Client Credentials: validate credentials and return JWT.
    Raises ValueError on failure.
    """
    pool = await get_core_primary_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM public.third_party_consumers WHERE client_id = $1",
            client_id,
        )

    if not row:
        raise ValueError("Invalid client credentials")

    if not bcrypt.checkpw(client_secret.encode(), row["client_secret_hash"].encode()):
        raise ValueError("Invalid client credentials")

    if row["status"] != "active":
        raise ValueError(f"Consumer is {row['status']}")

    # Determine scopes
    assigned_scopes = row["scopes"] or []
    if requested_scope:
        requested = requested_scope.split()
        for scope in requested:
            if scope not in assigned_scopes:
                raise ValueError(f"Scope '{scope}' not assigned to this consumer")
        token_scopes = requested
    else:
        token_scopes = assigned_scopes

    # Generate JWT
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(row["consumer_id"]),
        "client_id": row["client_id"],
        "scopes": token_scopes,
        "iat": now,
        "exp": now + timedelta(seconds=settings.JWT_EXPIRY_SECONDS),
        "jti": str(uuid4()),
        "iss": "payment-gateway",
    }

    access_token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": settings.JWT_EXPIRY_SECONDS,
        "scope": " ".join(token_scopes),
    }


def validate_token(token: str) -> dict:
    """Verify JWT and return payload. Raises JWTError on failure."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")
