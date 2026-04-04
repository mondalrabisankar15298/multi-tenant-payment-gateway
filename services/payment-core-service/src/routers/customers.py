from fastapi import APIRouter, HTTPException, Depends
from ..models.schemas import CustomerCreate, CustomerUpdate, CustomerResponse
from ..services import customer_service
from ..utils.auth import verify_merchant_access

router = APIRouter(
    prefix="/api/{merchant_id}/customers", 
    tags=["customers"],
    dependencies=[Depends(verify_merchant_access)]
)


@router.post("", response_model=CustomerResponse, status_code=201)
async def create_customer(merchant_id: int, data: CustomerCreate):
    try:
        customer = await customer_service.create_customer(
            merchant_id, data.name, data.email, data.phone
        )
        return customer
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_customers(merchant_id: int, page: int = 1, limit: int = 25):
    data, total = await customer_service.list_customers(merchant_id, page, limit)
    return {
        "data": data,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit,
    }


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(merchant_id: int, customer_id: str):
    customer = await customer_service.get_customer(merchant_id, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(merchant_id: int, customer_id: str, data: CustomerUpdate):
    customer = await customer_service.update_customer(
        merchant_id, customer_id, data.name, data.email, data.phone
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.delete("/{customer_id}", status_code=204)
async def delete_customer(merchant_id: int, customer_id: str):
    deleted = await customer_service.delete_customer(merchant_id, customer_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Customer not found")
