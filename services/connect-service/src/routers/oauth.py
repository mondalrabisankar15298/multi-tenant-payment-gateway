"""
OAuth 2.0 Token Endpoint — Client Credentials Flow (RFC 6749)

POST /api/v1/oauth/token
"""
import logging
from fastapi import APIRouter, HTTPException, Form
from ..services.oauth_service import authenticate_consumer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/oauth", tags=["OAuth"])


@router.post("/token")
async def token_endpoint(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    scope: str = Form(None),
):
    """
    OAuth 2.0 Client Credentials token endpoint.

    - grant_type: must be "client_credentials"
    - client_id: consumer's client ID
    - client_secret: consumer's client secret
    - scope: (optional) space-separated list of scopes (must be subset of assigned)
    """
    if grant_type != "client_credentials":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_grant_type",
                "message": "Only 'client_credentials' grant type is supported",
            },
        )

    try:
        result = await authenticate_consumer(client_id, client_secret, scope)
        return result
    except ValueError as e:
        error_msg = str(e)
        if "credentials" in error_msg.lower():
            raise HTTPException(status_code=401, detail={"error": "invalid_client", "message": error_msg})
        elif "suspended" in error_msg.lower() or "revoked" in error_msg.lower():
            raise HTTPException(status_code=403, detail={"error": "access_denied", "message": error_msg})
        else:
            raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": error_msg})
