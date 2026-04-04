"""
Cursor-based pagination utilities.
Cursor strategy: Base64-encoded (updated_at, entity_id) tuple.
"""
import base64
import json
from datetime import datetime


def encode_cursor(updated_at: datetime, entity_id: str) -> str:
    """Encode a pagination cursor from timestamp + entity ID."""
    payload = {"t": updated_at.isoformat(), "id": str(entity_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Decode a pagination cursor. Returns (updated_at, entity_id)."""
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor))
        return datetime.fromisoformat(payload["t"]), payload["id"]
    except Exception:
        raise ValueError("Invalid cursor format")
