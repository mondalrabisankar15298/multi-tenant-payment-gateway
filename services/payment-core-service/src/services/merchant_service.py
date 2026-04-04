import time
from datetime import datetime, timezone
from ..database import get_pool
from uuid6 import uuid7
from ..utils.event_emitter import emit_event


async def create_merchant(name: str, email: str) -> dict:
    """Create a new merchant with its own schema and tables."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. Insert merchant record
            api_key = uuid7()
            now = datetime.now(timezone.utc)
            merchant = await conn.fetchrow(
                """
                INSERT INTO public.merchants (name, email, schema_name, api_key, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $5)
                RETURNING *
                """,
                name, email, "", api_key, now
            )
            merchant_id = merchant["merchant_id"]
            schema_name = f"m_{uuid7().hex}"

            # Update schema_name and refreshed updated_at
            await conn.execute(
                "UPDATE public.merchants SET schema_name = $1, updated_at = $3 WHERE merchant_id = $2",
                schema_name, merchant_id, datetime.now(timezone.utc)
            )

            # 2. Create tenant schema + tables (DUAL ID: BIGSERIAL internal PK + UUID external key)
            await conn.execute(f"CREATE SCHEMA {schema_name}")

            await conn.execute(f"""
                CREATE TABLE {schema_name}.customers (
                    id            BIGSERIAL PRIMARY KEY,
                    customer_id   UUID UNIQUE NOT NULL,
                    name          VARCHAR(255) NOT NULL,
                    email         VARCHAR(255),
                    phone         VARCHAR(50),
                    created_at    TIMESTAMPTZ DEFAULT NOW(),
                    updated_at    TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute(f"""
                CREATE TABLE {schema_name}.payments (
                    id            BIGSERIAL PRIMARY KEY,
                    payment_id    UUID UNIQUE NOT NULL,
                    customer_ref  BIGINT NOT NULL REFERENCES {schema_name}.customers(id),
                    amount        DECIMAL(12,2) NOT NULL,
                    currency      VARCHAR(3) DEFAULT 'INR',
                    status        VARCHAR(30) DEFAULT 'created',
                    method        VARCHAR(30) NOT NULL,
                    description   TEXT,
                    metadata      JSONB DEFAULT '{{}}'::jsonb,
                    failure_reason VARCHAR(255),
                    amount_refunded DECIMAL(12,2) DEFAULT 0.00,
                    created_at    TIMESTAMPTZ DEFAULT NOW(),
                    updated_at    TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute(f"""
                CREATE TABLE {schema_name}.refunds (
                    id            BIGSERIAL PRIMARY KEY,
                    refund_id     UUID UNIQUE NOT NULL,
                    payment_ref   BIGINT NOT NULL REFERENCES {schema_name}.payments(id),
                    amount        DECIMAL(12,2) NOT NULL,
                    reason        TEXT,
                    status        VARCHAR(30) DEFAULT 'initiated',
                    created_at    TIMESTAMPTZ DEFAULT NOW(),
                    updated_at    TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute(f"""
                CREATE TABLE {schema_name}.ledger_entries (
                    id            BIGSERIAL PRIMARY KEY,
                    ledger_id     UUID UNIQUE NOT NULL,
                    payment_ref   BIGINT REFERENCES {schema_name}.payments(id),
                    refund_ref    BIGINT REFERENCES {schema_name}.refunds(id),
                    entry_type    VARCHAR(30) NOT NULL,
                    amount        DECIMAL(12,2) NOT NULL,
                    balance_after DECIMAL(12,2) NOT NULL,
                    created_at    TIMESTAMPTZ DEFAULT NOW(),
                    updated_at    TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # 3. Emit domain event
            merchant_data = dict(merchant)
            merchant_data["schema_name"] = schema_name
            await emit_event(
                conn,
                merchant_id=merchant_id,
                schema_name=schema_name,
                event_type="merchant.created.v1",
                entity_type="merchant",
                entity_id=str(merchant_id),
                payload=merchant_data,
            )

            # Refetch with updated schema_name
            result = await conn.fetchrow(
                "SELECT * FROM public.merchants WHERE merchant_id = $1",
                merchant_id
            )
            return dict(result)


async def update_merchant(merchant_id: int, name: str = None, email: str = None, status: str = None) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Update public.merchants
            updated = await conn.fetchrow(
                """
                UPDATE public.merchants 
                SET name = COALESCE($1, name),
                    email = COALESCE($2, email),
                    status = COALESCE($3, status),
                    updated_at = $5
                WHERE merchant_id = $4
                RETURNING *
                """,
                name, email, status, merchant_id, datetime.now(timezone.utc)
            )
            if not updated:
                raise ValueError(f"Merchant {merchant_id} not found")
                
            merchant_data = dict(updated)
            await emit_event(
                conn,
                merchant_id=merchant_id,
                schema_name=merchant_data["schema_name"],
                event_type="merchant.updated.v1",
                entity_type="merchant",
                entity_id=str(merchant_id),
                payload=merchant_data,
            )
            return merchant_data


_schema_cache = {}
_SCHEMA_CACHE_TTL = 300  # 5 minutes

async def get_merchant_schema(merchant_id: int) -> str:
    now = time.time()
    if merchant_id in _schema_cache:
        schema, expires_at = _schema_cache[merchant_id]
        if now < expires_at:
            return schema

    merchant = await get_merchant(merchant_id)
    if not merchant:
        raise ValueError(f"Merchant {merchant_id} not found")
    
    from ..utils.validators import validate_schema_name
    schema = validate_schema_name(merchant["schema_name"])
    
    _schema_cache[merchant_id] = (schema, now + _SCHEMA_CACHE_TTL)
    return schema


async def list_merchants(page: int = 1, limit: int = 25) -> tuple[list[dict], int]:
    pool = await get_pool()
    offset = (page - 1) * limit
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM public.merchants"
        )
        rows = await conn.fetch(
            "SELECT * FROM public.merchants ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
        return [dict(r) for r in rows], total


async def get_merchant(merchant_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM public.merchants WHERE merchant_id = $1",
            merchant_id
        )
        return dict(row) if row else None
