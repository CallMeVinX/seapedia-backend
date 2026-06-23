import uuid
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class StoreCreateRequest(BaseModel):
    store_name: str

class StoreStatusResponse(BaseModel):
    has_store: bool
    store_name: Optional[str] = None
    store_id: Optional[int] = None

class StoreResponse(BaseModel):
    id: int
    seller_id: uuid.UUID
    store_name: str
    logo_url: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
