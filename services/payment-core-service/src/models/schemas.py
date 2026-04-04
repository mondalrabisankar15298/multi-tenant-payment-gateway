from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID
from decimal import Decimal
from pydantic import condecimal


# ─── Merchant ─────────────────────────────────────────────

class MerchantCreate(BaseModel):
    name: str
    email: str


class MerchantUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    status: Optional[Literal["active", "suspended"]] = None


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
    amount: condecimal(gt=0, max_digits=12, decimal_places=2)
    currency: Literal["INR", "USD", "EUR"] = "INR"
    method: Literal["card", "upi", "netbanking", "wallet"]
    description: Optional[str] = None
    metadata: Optional[dict] = None


class PaymentUpdate(BaseModel):
    description: Optional[str] = None
    metadata: Optional[dict] = None


class PaymentResponse(BaseModel):
    payment_id: UUID
    customer_id: UUID
    amount: Decimal
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
    amount: condecimal(gt=0, max_digits=12, decimal_places=2)
    reason: Optional[str] = None


class RefundResponse(BaseModel):
    refund_id: UUID
    payment_id: UUID
    amount: Decimal
    reason: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime


# ─── Pagination ───────────────────────────────────────────

class PaginatedResponse(BaseModel):
    data: list
    total: int
    page: int
    limit: int
    total_pages: int


# ─── Pagination ───────────────────────────────────────────

class PaginatedResponse(BaseModel):
    data: list
    total: int
    page: int
    limit: int
    total_pages: int
