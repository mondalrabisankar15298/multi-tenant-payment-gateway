import json
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
            merchant = await conn.fetchrow(
                """
                INSERT INTO public.merchants (name, email, schema_name, api_key)
                VALUES ($1, $2, $3, $4)
                RETURNING *
                """,
                name, email, "", api_key
            )
            merchant_id = merchant["merchant_id"]
            schema_name = f"merchant_{merchant_id}"

            # Update schema_name
            await conn.execute(
                "UPDATE public.merchants SET schema_name = $1 WHERE merchant_id = $2",
                schema_name, merchant_id
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


async def list_merchants() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM public.merchants ORDER BY created_at DESC")
        return [dict(r) for r in rows]


async def get_merchant(merchant_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM public.merchants WHERE merchant_id = $1",
            merchant_id
        )
        return dict(row) if row else None
