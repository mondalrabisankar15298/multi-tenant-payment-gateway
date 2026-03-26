from ..database import get_pool
from ..utils.event_emitter import emit_event
from uuid6 import uuid7


async def create_refund(merchant_id: int, payment_id: str, amount: float,
                        reason: str = None) -> dict:
    schema = f"merchant_{merchant_id}"
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Resolve payment UUID → internal BIGINT id
            pay = await conn.fetchrow(
                f"SELECT id, payment_id, amount, status, customer_ref FROM {schema}.payments WHERE payment_id = $1",
                payment_id
            )
            if not pay:
                raise ValueError("Payment not found")
            if pay["status"] not in ("captured", "settled"):
                raise ValueError(f"Cannot refund payment with status: {pay['status']}")
            if amount > float(pay["amount"]):
                raise ValueError("Refund amount exceeds payment amount")

            payment_internal_id = pay["id"]

            # Resolve customer UUID for event payload
            cust = await conn.fetchrow(
                f"SELECT customer_id FROM {schema}.customers WHERE id = $1",
                pay["customer_ref"],
            )

            # Insert refund with BIGINT FK
            refund_id = uuid7()
            row = await conn.fetchrow(
                f"""
                INSERT INTO {schema}.refunds (refund_id, payment_ref, amount, reason)
                VALUES ($1, $2, $3, $4)
                RETURNING refund_id, payment_ref, amount, reason, status, created_at, updated_at
                """,
                refund_id, payment_internal_id, amount, reason,
            )

            # Build external response (swap payment_ref → payment_id UUID)
            refund = dict(row)
            refund["payment_id"] = str(pay["payment_id"])
            refund.pop("payment_ref", None)

            # Ledger entry using BIGINT refs
            ledger_uuid = uuid7()
            internal_refund_id = await conn.fetchval(
                f"SELECT id FROM {schema}.refunds WHERE refund_id = $1", refund_id
            )
            await conn.execute(
                f"""
                INSERT INTO {schema}.ledger_entries
                    (ledger_id, payment_ref, refund_ref, entry_type, amount, balance_after)
                VALUES ($1, $2, $3, 'refund_issued', $4,
                    (SELECT COALESCE(SUM(CASE WHEN entry_type LIKE 'payment%%' THEN amount ELSE -amount END), 0)
                     FROM {schema}.ledger_entries) - $4)
                """,
                ledger_uuid, payment_internal_id, internal_refund_id, amount,
            )

            # Emit event with UUID-only payload
            event_payload = {**refund, "payment_amount": float(pay["amount"])}
            if cust:
                event_payload["customer_id"] = str(cust["customer_id"])
            await emit_event(
                conn,
                merchant_id=merchant_id,
                schema_name=schema,
                event_type="refund.initiated.v1",
                entity_type="refund",
                entity_id=str(refund["refund_id"]),
                payload=event_payload,
            )
            return refund


async def process_refund(merchant_id: int, refund_id: str) -> dict | None:
    schema = f"merchant_{merchant_id}"
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                f"SELECT * FROM {schema}.refunds WHERE refund_id = $1 FOR UPDATE",
                refund_id,
            )
            if not row:
                return None
            if row["status"] != "initiated":
                raise ValueError(f"Cannot process refund with status: {row['status']}")

            updated_row = await conn.fetchrow(
                f"""
                UPDATE {schema}.refunds
                SET status = 'processed', updated_at = NOW()
                WHERE refund_id = $1
                RETURNING refund_id, payment_ref, amount, reason, status, created_at, updated_at
                """,
                refund_id,
            )

            # Resolve payment UUID for response
            pay = await conn.fetchrow(
                f"SELECT payment_id FROM {schema}.payments WHERE id = $1",
                updated_row["payment_ref"],
            )

            updated = dict(updated_row)
            updated["payment_id"] = str(pay["payment_id"]) if pay else None
            updated.pop("payment_ref", None)

            await emit_event(
                conn,
                merchant_id=merchant_id,
                schema_name=schema,
                event_type="refund.processed.v1",
                entity_type="refund",
                entity_id=str(refund_id),
                payload=updated,
            )
            return updated


async def list_refunds(merchant_id: int) -> list[dict]:
    schema = f"merchant_{merchant_id}"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT r.refund_id, p.payment_id, r.amount, r.reason, r.status,
                   r.created_at, r.updated_at
            FROM {schema}.refunds r
            JOIN {schema}.payments p ON p.id = r.payment_ref
            ORDER BY r.created_at DESC
            """
        )
        return [dict(r) for r in rows]
