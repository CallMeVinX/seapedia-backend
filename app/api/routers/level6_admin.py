from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.api.dependencies import RequireActiveRole
from app.models.voucher import Voucher
from app.models.promo import Promo
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["Admin Discounts"])

class DiscountCreateRequest(BaseModel):
    """
    Schema for creating a new discount.
    Validates the structure of the incoming request payload to ensure data consistency before hitting the database.
    """
    code: str
    discount_value: float
    discount_type: str 
    min_order_value: float
    max_usage: Optional[int] = None
    expiry_date: str

class DiscountUpdateRequest(BaseModel):
    """
    Schema for partially updating an existing discount.
    All fields are optional to allow for patching specific attributes without requiring the full object representation.
    """
    code: Optional[str] = None
    discount_value: Optional[float] = None
    discount_type: Optional[str] = None
    min_order_value: Optional[float] = None
    max_usage: Optional[int] = None
    expiry_date: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/admin/discounts")
async def get_discounts(
    payload: dict = Depends(RequireActiveRole(["Admin"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetches all active vouchers in the system.
    Filters out logically deleted records to prevent inactive discounts from being displayed in the administrative panel.
    """
    now = datetime.now(timezone.utc)
    results = []
    
    stmt = select(Voucher).where(Voucher.is_deleted == False)
    vouchers = (await db.execute(stmt)).scalars().all()
    for v in vouchers:
        results.append({
            "id": v.id,
            "code": v.code,
            "type": "voucher",
            "discount_value": float(v.amount),
            "discount_type": v.discount_type.lower(),
            "min_order_value": float(v.min_purchase),
            "max_usage": v.remaining_usage,
            "current_usage": 0,
            "expiry_date": v.valid_until.isoformat() if v.valid_until else None,
            "is_active": v.valid_until > now,
            "created_at": v.created_at.isoformat() if v.created_at else None
        })
            
    return results

@router.post("/admin/discounts")
async def create_discount(
    data: DiscountCreateRequest,
    payload: dict = Depends(RequireActiveRole(["Admin"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a new discount voucher.
    Includes explicit rollback on failure to maintain database integrity against duplicate constraint violations.
    """
    try:
        valid_until = datetime.fromisoformat(data.expiry_date.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Format expiry_date tidak valid.")
        
    new_voucher = Voucher(
        code=data.code.strip().upper(),
        discount_type=data.discount_type.upper(),
        amount=data.discount_value,
        min_purchase=data.min_order_value,
        remaining_usage=data.max_usage,
        valid_from=datetime.now(timezone.utc),
        valid_until=valid_until
    )
    db.add(new_voucher)
    try:
        await db.commit()
        await db.refresh(new_voucher)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Kode voucher sudah digunakan atau data tidak valid.")
        
    now = datetime.now(timezone.utc)
    return {
        "id": new_voucher.id,
        "code": new_voucher.code,
        "type": "voucher",
        "discount_value": float(new_voucher.amount),
        "discount_type": new_voucher.discount_type.lower(),
        "min_order_value": float(new_voucher.min_purchase),
        "max_usage": new_voucher.remaining_usage,
        "current_usage": 0,
        "expiry_date": new_voucher.valid_until.isoformat(),
        "is_active": not new_voucher.is_deleted and new_voucher.valid_until > now,
        "created_at": new_voucher.created_at.isoformat() if new_voucher.created_at else None
    }

@router.put("/admin/discounts/{id}")
async def update_discount(
    id: int,
    data: DiscountUpdateRequest,
    payload: dict = Depends(RequireActiveRole(["Admin"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Updates specific attributes of an existing discount voucher.
    Applies changes conditionally to avoid overwriting existing properties with null values when partial updates are provided.
    """
    voucher = await db.scalar(select(Voucher).where(Voucher.id == id, Voucher.is_deleted == False))
    if voucher:
        if data.code is not None:
            voucher.code = data.code
        if data.discount_value is not None:
            voucher.amount = data.discount_value
        if data.discount_type is not None:
            voucher.discount_type = data.discount_type.upper()
        if data.min_order_value is not None:
            voucher.min_purchase = data.min_order_value
        if data.max_usage is not None:
            voucher.remaining_usage = data.max_usage
        if data.expiry_date is not None:
            voucher.valid_until = datetime.fromisoformat(data.expiry_date.replace("Z", "+00:00"))
        
        await db.commit()
        return {"message": "Voucher updated"}
        
    raise HTTPException(status_code=404, detail="Discount not found")

@router.delete("/admin/discounts/{id}")
async def delete_discount(
    id: int,
    payload: dict = Depends(RequireActiveRole(["Admin"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Soft-deletes a discount voucher to maintain historical references in past orders.
    It marks the voucher as deleted rather than removing the row entirely.
    """
    voucher = await db.scalar(select(Voucher).where(Voucher.id == id, Voucher.is_deleted == False))
    if voucher:
        voucher.is_deleted = True
        await db.commit()
        return {"message": "Voucher deleted"}
        
    raise HTTPException(status_code=404, detail="Discount not found")
