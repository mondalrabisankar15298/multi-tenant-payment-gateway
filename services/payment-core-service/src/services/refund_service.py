from uuid6 import uuid7
from datetime import datetime, timezone
from ..database import get_pool
from .merchant_service import get_merchant_schema
from ..utils.event_emitter import emit_event
from decimal import Decimal


async def create_refund(merchant_id: int, payment_id: str, amount: Decimal,
                        reason: str = None) -> dict:
    schema = await get_merchant_schema(merchant_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Resolve payment UUID → internal BIGINT id
            pay = await conn.fetchrow(
                f"SELECT id, payment_id, amount, amount_refunded, status, customer_ref FROM {schema}.payments WHERE payment_id = $1 FOR UPDATE",
                payment_id
            )
            if not pay:
                raise ValueError("Payment not found")
            if pay["status"] not in ("captured", "settled"):
                raise ValueError(f"Cannot refund payment with status: {pay['status']}")

            refund_remaining = Decimal(str(pay["amount"])) - Decimal(str(pay.get("amount_refunded") or 0))
            if amount > refund_remaining:
                raise ValueError(f"Refund amount ({amount}) exceeds remaining payment balance ({refund_remaining})")

            payment_internal_id = pay["id"]

            # Atomically reserve the refunded amount on the payment record
            await conn.execute(
                f"UPDATE {schema}.payments SET amount_refunded = amount_refunded + $1 WHERE id = $2",
                amount, payment_internal_id
            )

            # Resolve customer UUID for event payload
            cust = await conn.fetchrow(
                f"SELECT customer_id FROM {schema}.customers WHERE id = $1",
                pay["customer_ref"],
            )

            # Insert refund with BIGINT FK and explicit UTC
            refund_id = uuid7()
            now = datetime.now(timezone.utc)
            row = await conn.fetchrow(
                f"""
                INSERT INTO {schema}.refunds (refund_id, payment_ref, amount, reason, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $5)
                RETURNING refund_id, payment_ref, amount, reason, status, created_at, updated_at
                """,
                refund_id, payment_internal_id, amount, reason, now
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
                    (ledger_id, payment_ref, refund_ref, entry_type, amount, balance_after, created_at, updated_at)
                VALUES ($1, $2, $3, 'refund_issued', $4,
                    (SELECT COALESCE(SUM(CASE WHEN entry_type LIKE 'payment%%' THEN amount ELSE -amount END), 0)
                     FROM {schema}.ledger_entries) - $4, $5, $5)
                """,
                ledger_uuid, payment_internal_id, internal_refund_id, amount, now
            )

            # Emit event with UUID-only payload
            event_payload = {**refund, "payment_amount": Decimal(str(pay["amount"]))}
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
    schema = await get_merchant_schema(merchant_id)
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
                SET status = 'processed', updated_at = $2
                WHERE refund_id = $1
                RETURNING refund_id, payment_ref, amount, reason, status, created_at, updated_at
                """,
                refund_id, datetime.now(timezone.utc)
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


async def list_refunds(merchant_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    schema = await get_merchant_schema(merchant_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT r.refund_id, p.payment_id, r.amount, r.reason, r.status,
                   r.created_at, r.updated_at
            FROM {schema}.refunds r
            JOIN {schema}.payments p ON p.id = r.payment_ref
            ORDER BY r.created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset
        )
        return [dict(r) for r in rows]
