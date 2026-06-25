from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from datetime import datetime

from enum import Enum

class OrderStatus(str, Enum):
    MENUNGGU_PEMBAYARAN = "Menunggu Pembayaran"
    SEDANG_DIKEMAS = "Sedang Dikemas"
    MENUNGGU_PENGIRIM = "Menunggu Pengirim"
    SEDANG_DIKIRIM = "Sedang Dikirim"
    PESANAN_SELESAI = "Pesanan Selesai"
    DIKEMBALIKAN = "Dikembalikan"
    DIBATALKAN = "Dibatalkan"

class CheckoutRequest(BaseModel):
    cart_item_ids: List[int] = Field(..., description="List of CartItem IDs to checkout")
    address_id: int
    delivery_method: str = Field(..., description="Method of delivery, e.g., INSTANT, NEXT_DAY, REGULAR")
    voucher_code: Optional[str] = None

class CheckoutResponse(BaseModel):
    order_id: int
    subtotal: Decimal
    promo_discount_amount: Decimal
    voucher_discount_amount: Decimal
    delivery_fee: Decimal
    ppn_amount: Decimal
    final_total: Decimal
    message: str = "Checkout successful"

class OrderStatusUpdateRequest(BaseModel):
    status: OrderStatus = Field(..., description="The new status to set for the order")

class OrderStatusHistoryResponse(BaseModel):
    id: int
    status_name: str
    changed_by_user_id: Optional[str] = None
    changed_by_role: Optional[str] = None
    created_at: datetime

class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    product_image: Optional[str] = None

class OrderResponse(BaseModel):
    id: int
    store_name: str
    current_status: str
    final_total: Decimal
    delivery_fee: Decimal
    shipping_address: Optional[str] = None
    created_at: datetime
    items: List[OrderItemResponse]
