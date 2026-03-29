from ..database import get_pool
from .merchant_service import get_merchant_schema
from datetime import datetime, timezone
from ..utils.event_emitter import emit_event
from uuid6 import uuid7


async def create_customer(merchant_id: int, name: str, email: str = None, phone: str = None) -> dict:
    schema = await get_merchant_schema(merchant_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            customer_id = uuid7()
            now = datetime.now(timezone.utc)
            customer = await conn.fetchrow(
                f"""
                INSERT INTO {schema}.customers (customer_id, name, email, phone, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $5)
                RETURNING customer_id, name, email, phone, created_at, updated_at
                """,
                customer_id, name, email, phone, now,
            )
            await emit_event(
                conn,
                merchant_id=merchant_id,
                schema_name=schema,
                event_type="customer.created.v1",
                entity_type="customer",
                entity_id=str(customer["customer_id"]),
                payload=dict(customer),
            )
            return dict(customer)


async def update_customer(merchant_id: int, customer_id: str,
                          name: str = None, email: str = None, phone: str = None) -> dict | None:
    schema = await get_merchant_schema(merchant_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                f"SELECT * FROM {schema}.customers WHERE customer_id = $1", customer_id
            )
            if not existing:
                return None

            updated = await conn.fetchrow(
                f"""
                UPDATE {schema}.customers
                SET name = COALESCE($1, name),
                    email = COALESCE($2, email),
                    phone = COALESCE($3, phone),
                    updated_at = $5
                WHERE customer_id = $4
                RETURNING customer_id, name, email, phone, created_at, updated_at
                """,
                name, email, phone, customer_id, datetime.now(timezone.utc),
            )
            await emit_event(
                conn,
                merchant_id=merchant_id,
                schema_name=schema,
                event_type="customer.updated.v1",
                entity_type="customer",
                entity_id=str(customer_id),
                payload=dict(updated),
            )
            return dict(updated)


async def delete_customer(merchant_id: int, customer_id: str) -> bool:
    schema = await get_merchant_schema(merchant_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                f"SELECT * FROM {schema}.customers WHERE customer_id = $1", customer_id
            )
            if not existing:
                return False

            await conn.execute(
                f"DELETE FROM {schema}.customers WHERE customer_id = $1", customer_id
            )
            await emit_event(
                conn,
                merchant_id=merchant_id,
                schema_name=schema,
                event_type="customer.deleted.v1",
                entity_type="customer",
                entity_id=str(customer_id),
                payload={"customer_id": str(customer_id)},
            )
            return True


async def list_customers(merchant_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    schema = await get_merchant_schema(merchant_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT customer_id, name, email, phone, created_at, updated_at FROM {schema}.customers ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
        return [dict(r) for r in rows]


async def get_customer(merchant_id: int, customer_id: str) -> dict | None:
    schema = await get_merchant_schema(merchant_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT customer_id, name, email, phone, created_at, updated_at FROM {schema}.customers WHERE customer_id = $1",
            customer_id
        )
        return dict(row) if row else None
