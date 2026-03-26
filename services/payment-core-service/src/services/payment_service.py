import json
from ..database import get_pool
from ..utils.event_emitter import emit_event
from uuid6 import uuid7

VALID_TRANSITIONS = {
    "created": ["authorized", "failed"],
    "authorized": ["captured"],
    "captured": ["settled"],
}


async def create_payment(merchant_id: int, customer_id: str, amount: float,
                         currency: str, method: str, description: str = None,
                         metadata: dict = None) -> dict:
    schema = f"merchant_{merchant_id}"
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Resolve customer UUID → internal BIGINT id
            cust = await conn.fetchrow(
                f"SELECT id, customer_id FROM {schema}.customers WHERE customer_id = $1",
                customer_id,
            )
            if not cust:
                raise ValueError(f"Customer {customer_id} not found")
            customer_internal_id = cust["id"]

            payment_id = uuid7()
            row = await conn.fetchrow(
                f"""
                INSERT INTO {schema}.payments
                    (payment_id, customer_ref, amount, currency, method, description, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                RETURNING id, payment_id, customer_ref, amount, currency, status, method,
                          description, metadata, failure_reason, created_at, updated_at
                """,
                payment_id, customer_internal_id, amount, currency, method, description,
                metadata or {},
            )

            # Build external-facing response (swap customer_ref BIGINT → customer_id UUID)
            payment = dict(row)
            payment["customer_id"] = str(cust["customer_id"])
            internal_id = payment.pop("id")
            payment.pop("customer_ref", None)

            # Ledger entry using internal BIGINT
            ledger_uuid = uuid7()
            await conn.execute(
                f"""
                INSERT INTO {schema}.ledger_entries
                    (ledger_id, payment_ref, entry_type, amount, balance_after)
                VALUES ($1, $2, 'payment_created', $3,
                    (SELECT COALESCE(SUM(CASE WHEN entry_type LIKE 'payment%%' THEN amount ELSE -amount END), 0)
                     FROM {schema}.ledger_entries) + $3)
                """,
                ledger_uuid, internal_id, amount,
            )

            # Emit event with UUID-only payload
            await emit_event(
                conn,
                merchant_id=merchant_id,
                schema_name=schema,
                event_type="payment.created.v1",
                entity_type="payment",
                entity_id=str(payment["payment_id"]),
                payload=payment,
            )
            return payment


async def transition_payment(merchant_id: int, payment_id: str, target_status: str,
                             failure_reason: str = None) -> dict | None:
    schema = f"merchant_{merchant_id}"
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                f"SELECT * FROM {schema}.payments WHERE payment_id = $1 FOR UPDATE",
                payment_id,
            )
            if not row:
                return None

            current_status = row["status"]
            allowed = VALID_TRANSITIONS.get(current_status, [])
            if target_status not in allowed:
                raise ValueError(
                    f"Invalid transition: {current_status} → {target_status}. "
                    f"Allowed: {allowed}"
                )

            update_fields = "status = $1, updated_at = NOW()"
            params = [target_status, payment_id]
            if failure_reason and target_status == "failed":
                update_fields += ", failure_reason = $3"
                params.append(failure_reason)

            updated_row = await conn.fetchrow(
                f"UPDATE {schema}.payments SET {update_fields} WHERE payment_id = $2 RETURNING *",
                *params,
            )

            # Resolve customer UUID for response
            cust = await conn.fetchrow(
                f"SELECT customer_id FROM {schema}.customers WHERE id = $1",
                updated_row["customer_ref"],
            )

            # Build external response
            updated = dict(updated_row)
            updated["customer_id"] = str(cust["customer_id"]) if cust else None
            internal_id = updated.pop("id")
            updated.pop("customer_ref", None)

            # Ledger entry for captured payments
            if target_status == "captured":
                ledger_uuid = uuid7()
                await conn.execute(
                    f"""
                    INSERT INTO {schema}.ledger_entries
                        (ledger_id, payment_ref, entry_type, amount, balance_after)
                    VALUES ($1, $2, 'payment_captured', $3,
                        (SELECT COALESCE(SUM(CASE WHEN entry_type LIKE 'payment%%' THEN amount ELSE -amount END), 0)
                         FROM {schema}.ledger_entries))
                    """,
                    ledger_uuid, internal_id, float(row["amount"]),
                )

            # Event type mapping
            event_type_map = {
                "authorized": "payment.authorized.v1",
                "captured": "payment.captured.v1",
                "failed": "payment.failed.v1",
                "settled": "payment.settled.v1",
            }
            await emit_event(
                conn,
                merchant_id=merchant_id,
                schema_name=schema,
                event_type=event_type_map[target_status],
                entity_type="payment",
                entity_id=str(payment_id),
                payload=updated,
            )
            return updated


async def list_payments(merchant_id: int) -> list[dict]:
    schema = f"merchant_{merchant_id}"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT p.payment_id, c.customer_id, p.amount, p.currency, p.status, p.method,
                   p.description, p.metadata, p.failure_reason, p.created_at, p.updated_at
            FROM {schema}.payments p
            JOIN {schema}.customers c ON c.id = p.customer_ref
            ORDER BY p.created_at DESC
            """
        )
        return [dict(r) for r in rows]


async def get_payment(merchant_id: int, payment_id: str) -> dict | None:
    schema = f"merchant_{merchant_id}"
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT p.payment_id, c.customer_id, p.amount, p.currency, p.status, p.method,
                   p.description, p.metadata, p.failure_reason, p.created_at, p.updated_at
            FROM {schema}.payments p
            JOIN {schema}.customers c ON c.id = p.customer_ref
            WHERE p.payment_id = $1
            """,
            payment_id
        )
        return dict(row) if row else None
