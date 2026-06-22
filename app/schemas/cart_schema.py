from pydantic import BaseModel, Field
from typing import List

class CartItemRequest(BaseModel):
    product_id: int
    quantity: int = Field(..., description="Quantity to add or remove (negative to remove)")

class CartItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_image: str | None = None
    store_id: int
    store_name: str
    quantity: int
    unit_price: int
    total_price: int

class CartResponse(BaseModel):
    id: int
    buyer_id: str
    items: List[CartItemResponse]
    total_items: int
    total_price: int
