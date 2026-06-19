from pydantic import BaseModel, ConfigDict
from decimal import Decimal
from typing import Optional

class ProductResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    price: Decimal
    stock: int
    image_url: Optional[str] = None
    images: list[str] = []
    store_name: str
    category_name: str

    model_config = ConfigDict(from_attributes=True)
