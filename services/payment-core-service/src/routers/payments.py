from fastapi import APIRouter, Depends, HTTPException
from ..models.schemas import PaymentCreate, PaymentResponse, PaymentUpdate
from ..services import payment_service
from ..utils.auth import verify_merchant_access

router = APIRouter(
    prefix="/api/{merchant_id}/payments",
    tags=["payments"],
    dependencies=[Depends(verify_merchant_access)]
)


@router.post("", response_model=PaymentResponse, status_code=201)
async def create_payment(merchant_id: int, data: PaymentCreate):
    try:
        payment = await payment_service.create_payment(
            merchant_id, data.customer_id, data.amount, data.currency,
            data.method, data.description, data.metadata
        )
        return payment
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_payments(merchant_id: int, page: int = 1, limit: int = 25):
    data, total = await payment_service.list_payments(merchant_id, page, limit)
    return {
        "data": data,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit,
    }


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(merchant_id: int, payment_id: str):
    payment = await payment_service.get_payment(merchant_id, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.put("/{payment_id}", response_model=PaymentResponse)
async def update_payment(merchant_id: int, payment_id: str, data: PaymentUpdate):
    try:
        payment = await payment_service.update_payment(
            merchant_id, payment_id, data.description, data.metadata
        )
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        return payment
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{payment_id}/authorize", response_model=PaymentResponse)
async def authorize_payment(merchant_id: int, payment_id: str):
    try:
        return await payment_service.transition_payment(merchant_id, payment_id, "authorized")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{payment_id}/capture", response_model=PaymentResponse)
async def capture_payment(merchant_id: int, payment_id: str):
    try:
        return await payment_service.transition_payment(merchant_id, payment_id, "captured")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{payment_id}/fail", response_model=PaymentResponse)
async def fail_payment(merchant_id: int, payment_id: str):
    try:
        return await payment_service.transition_payment(
            merchant_id, payment_id, "failed", failure_reason="Payment declined"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{payment_id}/settle", response_model=PaymentResponse)
async def settle_payment(merchant_id: int, payment_id: str):
    try:
        return await payment_service.transition_payment(merchant_id, payment_id, "settled")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
