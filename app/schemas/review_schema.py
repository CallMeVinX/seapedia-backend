from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional
from pydantic.types import conint

class ReviewCreateRequest(BaseModel):
    reviewer_name: str = Field(..., max_length=150)
    rating: conint(ge=1, le=5)
    comment: str

class ReviewResponse(BaseModel):
    id: str
    reviewer_name: str
    rating: int
    comment: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
