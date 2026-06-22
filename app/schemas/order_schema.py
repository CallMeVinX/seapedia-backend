from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal

class CheckoutRequest(BaseModel):
    cart_item_ids: List[int] = Field(..., description="List of CartItem IDs to checkout")
    address_id: int
    delivery_method: str = Field(..., description="Method of delivery, e.g., INSTANT, NEXT_DAY, REGULAR")
    discount_code: Optional[str] = None

class CheckoutResponse(BaseModel):
    order_id: int
    subtotal: Decimal
    discount_amount: Decimal
    delivery_fee: Decimal
    ppn_amount: Decimal
    final_total: Decimal
    message: str = "Checkout successful"
