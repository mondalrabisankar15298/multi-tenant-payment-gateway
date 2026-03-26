from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date, datetime
from uuid import UUID


# ─── Merchant ─────────────────────────────────────────────

class MerchantCreate(BaseModel):
    name: str
    email: str


class MerchantResponse(BaseModel):
    merchant_id: int
    name: str
    email: str
    schema_name: str
    api_key: UUID
    status: str
    created_at: datetime


# ─── Customer ─────────────────────────────────────────────

class CustomerCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class CustomerResponse(BaseModel):
    customer_id: UUID
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ─── Payment ──────────────────────────────────────────────

class PaymentCreate(BaseModel):
    customer_id: UUID
    amount: float
    currency: str = "INR"
    method: str  # card | upi | netbanking | wallet
    description: Optional[str] = None
    metadata: Optional[dict] = {}


class PaymentResponse(BaseModel):
    payment_id: UUID
    customer_id: UUID
    amount: float
    currency: str
    status: str
    method: str
    description: Optional[str] = None
    metadata: Optional[dict] = None
    failure_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ─── Refund ───────────────────────────────────────────────

class RefundCreate(BaseModel):
    amount: float
    reason: Optional[str] = None


class RefundResponse(BaseModel):
    refund_id: UUID
    payment_id: UUID
    amount: float
    reason: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime
