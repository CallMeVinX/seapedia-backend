from pydantic import BaseModel, Field

class AddressRequest(BaseModel):
    full_address: str = Field(..., description="Full delivery address")

class AddressResponse(BaseModel):
    id: int
    buyer_id: str
    full_address: str
