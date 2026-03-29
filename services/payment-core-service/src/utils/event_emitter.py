import json
from uuid6 import uuid7
from datetime import datetime, timezone


async def emit_event(conn, merchant_id: int, schema_name: str, event_type: str,
                     entity_type: str, entity_id: str, payload: dict):
    """Insert a domain event into the outbox table within an existing transaction."""
    # Serialize datetime objects in payload
    serialized_payload = json.dumps(payload, default=str)
    now = datetime.now(timezone.utc)

    await conn.execute(
        """
        INSERT INTO public.domain_events
            (event_id, merchant_id, schema_name, event_type, entity_type, entity_id, payload, status, created_at, updated_at)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7::jsonb, 'pending', $8, $8)
        """,
        uuid7(),
        merchant_id,
        schema_name,
        event_type,
        entity_type,
        entity_id,
        serialized_payload,
        now,
    )
