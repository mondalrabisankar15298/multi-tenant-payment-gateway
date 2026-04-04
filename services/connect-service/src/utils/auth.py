"""
Authentication middleware for third-party API access and admin access.
"""
import logging
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..services.oauth_service import validate_token, get_cached_consumer, check_merchant_access
from ..config import settings

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


async def verify_third_party_access(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    Validate Bearer JWT for third-party API access.

    Steps:
    1. Extract Bearer token
    2. Verify JWT signature + expiry
    3. Check consumer status (Redis-cached, Primary on miss)
    4. If X-Merchant-ID present, verify merchant access
    5. Attach consumer info to request.state
    """
    if not credentials:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": "Missing Authorization header", "code": "MISSING_TOKEN"})

    try:
        payload = validate_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": str(e), "code": "INVALID_TOKEN"})

    consumer_id = payload.get("sub")
    if not consumer_id:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": "Invalid token payload", "code": "INVALID_TOKEN"})

    # Check consumer status (Redis-cached)
    consumer = await get_cached_consumer(consumer_id)
    if not consumer:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": "Consumer not found", "code": "CONSUMER_NOT_FOUND"})

    if consumer.get("status") != "active":
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": f"Consumer is {consumer.get('status')}", "code": "CONSUMER_INACTIVE"})

    # Check merchant access if X-Merchant-ID header present
    merchant_id_str = request.headers.get("X-Merchant-ID")
    if merchant_id_str:
        try:
            merchant_id = int(merchant_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": "X-Merchant-ID must be an integer", "code": "INVALID_MERCHANT_ID"})

        has_access = await check_merchant_access(consumer_id, merchant_id)
        if not has_access:
            raise HTTPException(status_code=403, detail={"error": "forbidden", "message": f"Consumer does not have access to merchant {merchant_id}", "code": "ACCESS_DENIED"})

        request.state.merchant_id = merchant_id

    # Attach consumer info to request
    request.state.consumer_id = consumer_id
    request.state.client_id = payload.get("client_id")
    request.state.scopes = payload.get("scopes", [])
    request.state.consumer = consumer

    return consumer


async def verify_admin_access(request: Request):
    """Validate X-Admin-Key header against ADMIN_API_KEY env var."""
    admin_key = request.headers.get("X-Admin-Key")
    if not admin_key:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": "Missing X-Admin-Key header", "code": "MISSING_ADMIN_KEY"})

    if admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Invalid admin API key", "code": "INVALID_ADMIN_KEY"})


def require_scope(required_scope: str):
    """FastAPI dependency factory — checks if the token has a specific scope."""
    async def _check_scope(request: Request):
        scopes = getattr(request.state, "scopes", [])
        if required_scope not in scopes:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "insufficient_scope",
                    "message": f"Token missing required scope: {required_scope}",
                    "code": "INSUFFICIENT_SCOPE",
                },
            )
    return _check_scope
