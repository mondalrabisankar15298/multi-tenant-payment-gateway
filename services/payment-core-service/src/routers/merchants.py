from fastapi import APIRouter, HTTPException
from ..models.schemas import MerchantCreate, MerchantResponse, MerchantUpdate
from ..services import merchant_service

router = APIRouter(prefix="/api/merchants", tags=["merchants"])


@router.post("", response_model=MerchantResponse, status_code=201)
async def create_merchant(data: MerchantCreate):
    try:
        merchant = await merchant_service.create_merchant(data.name, data.email)
        return merchant
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_merchants(page: int = 1, limit: int = 25):
    data, total = await merchant_service.list_merchants(page, limit)
    return {
        "data": data,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit,
    }


@router.get("/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(merchant_id: int):
    merchant = await merchant_service.get_merchant(merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


@router.put("/{merchant_id}", response_model=MerchantResponse)
async def update_merchant(merchant_id: int, data: MerchantUpdate):
    try:
        merchant = await merchant_service.update_merchant(
            merchant_id, data.name, data.email, data.status
        )
        return merchant
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
