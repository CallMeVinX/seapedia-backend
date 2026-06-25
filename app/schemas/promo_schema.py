from pydantic import BaseModel, Field, validator
from typing import Optional, List
from decimal import Decimal
from datetime import datetime

class PromoCreateRequest(BaseModel):
    name: str = Field(..., max_length=150, description="Name of the promo")
    discount_percentage: Decimal = Field(..., gt=0, le=100, description="Discount percentage (e.g. 10.50)")
    valid_from: datetime = Field(..., description="Start date of the promo")
    valid_until: datetime = Field(..., description="End date of the promo")
    product_ids: List[int] = Field(..., description="List of product IDs to apply this promo to")

    @validator("valid_until")
    def end_date_must_be_after_start_date(cls, v, values):
        if "valid_from" in values and v <= values["valid_from"]:
            raise ValueError("valid_until must be after valid_from")
        return v

class PromoResponse(BaseModel):
    id: int
    store_id: int
    name: str
    discount_percentage: Decimal
    valid_from: datetime
    valid_until: datetime
    is_active: bool
    created_at: datetime
    product_ids: List[int] = []

    class Config:
        from_attributes = True

class PromoUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    discount_percentage: Optional[Decimal] = Field(None, gt=0, le=100)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    is_active: Optional[bool] = None
    product_ids: Optional[List[int]] = None
