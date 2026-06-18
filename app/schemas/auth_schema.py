from pydantic import BaseModel, EmailStr
from typing import List, Optional

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    roles: Optional[List[str]] = None

class SelectRoleRequest(BaseModel):
    chosen_role: str

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    owned_roles: List[str]
    active_role: Optional[str] = None

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    id: str
    email: str
    full_name: str
    roles: List[str]

class FinancialsResponse(BaseModel):
    walletBalance: float = 0.0
    sellerIncome: float = 0.0
    driverEarnings: float = 0.0

class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    roles: List[str]
    active_role: Optional[str] = None
    financials: FinancialsResponse


