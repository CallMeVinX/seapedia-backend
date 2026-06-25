from pydantic import BaseModel, Field, validator
from typing import Optional
from decimal import Decimal
from datetime import datetime

class VoucherCreateRequest(BaseModel):
    code: str = Field(..., max_length=50, description="Alphanumeric voucher code")
    discount_type: str = Field(..., description="PERCENTAGE or FIXED")
    amount: Decimal = Field(..., gt=0, description="Discount amount (% or fixed value)")
    min_purchase: Decimal = Field(0.00, ge=0, description="Minimum purchase amount required")
    max_discount: Optional[Decimal] = Field(None, ge=0, description="Maximum discount for PERCENTAGE type")
    remaining_usage: Optional[int] = Field(None, ge=0, description="Number of times this voucher can be used")
    valid_from: datetime = Field(..., description="Start date")
    valid_until: datetime = Field(..., description="Expiry date")

    @validator("valid_until")
    def end_date_must_be_after_start_date(cls, v, values):
        if "valid_from" in values and v <= values["valid_from"]:
            raise ValueError("valid_until must be after valid_from")
        return v

    @validator("discount_type")
    def validate_discount_type(cls, v):
        if v.upper() not in ["PERCENTAGE", "FIXED"]:
            raise ValueError("discount_type must be PERCENTAGE or FIXED")
        return v.upper()

class VoucherResponse(BaseModel):
    id: int
    code: str
    discount_type: str
    amount: Decimal
    min_purchase: Decimal
    max_discount: Optional[Decimal]
    remaining_usage: Optional[int]
    valid_from: datetime
    valid_until: datetime
    is_deleted: bool
    created_at: datetime

    class Config:
        from_attributes = True

class VoucherUpdateRequest(BaseModel):
    discount_type: Optional[str] = None
    amount: Optional[Decimal] = Field(None, gt=0)
    min_purchase: Optional[Decimal] = Field(None, ge=0)
    max_discount: Optional[Decimal] = Field(None, ge=0)
    remaining_usage: Optional[int] = Field(None, ge=0)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    is_deleted: Optional[bool] = None

class ValidateVoucherRequest(BaseModel):
    voucher_code: str
    subtotal: Decimal

class ValidateVoucherResponse(BaseModel):
    is_valid: bool
    code: str
    amount: Decimal
    message: str
