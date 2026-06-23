from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from datetime import datetime

class WalletResponse(BaseModel):
    id: int
    balance: Decimal
    transactions: List['WalletTransactionResponse'] = []

class WalletTransactionResponse(BaseModel):
    id: int
    amount: Decimal
    transaction_type: str
    description: Optional[str] = None
    created_at: datetime

class TopUpRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, le=10000000, description="Jumlah top-up (min 1, max 10.000.000)")
