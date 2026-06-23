from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.api.dependencies import RequireActiveRole, get_current_user_id
from app.models.user import User
from app.models.order import Order, DeliveryJob
from app.models.product import Product
from app.models.product import Store
from datetime import datetime

router = APIRouter(tags=["Dashboards"])

# Admin Dashboard
@router.get("/admin/dashboard/stats")
async def get_admin_dashboard_stats(
    payload: dict = Depends(RequireActiveRole(["Admin"])),
    db: AsyncSession = Depends(get_db)
):
    users_count = await db.scalar(select(func.count(User.id)))
    orders_count = await db.scalar(select(func.count(Order.id)))
    overdue_count = await db.scalar(
        select(func.count(Order.id)).where(Order.current_status == 'Overdue')
    )
    
    return {
        "users": users_count or 0,
        "orders": orders_count or 0,
        "overdue_orders": overdue_count or 0
    }

# Seller Dashboard
@router.get("/seller/dashboard/stats")
async def get_seller_dashboard_stats(
    payload: dict = Depends(RequireActiveRole(["Seller"])),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    # Get Seller Store
    store = await db.scalar(select(Store).where(Store.seller_id == user_id))
    if not store:
        return {
            "total_sales": 0, 
            "action_center": {"perlu_diproses": 0, "siap_dikirim": 0, "stok_kritis": 0},
            "chart_data": [],
            "low_stock_products": [],
            "orders_queue": []
        }
    
    # Action Center Counts
    from app.schemas.order_schema import OrderStatus
    
    # Total Sales (Only completed orders)
    total_sales = await db.scalar(
        select(func.sum(Order.final_total)).where(
            Order.store_id == store.id,
            Order.current_status == OrderStatus.PESANAN_SELESAI.value
        )
    )
    
    perlu_diproses = await db.scalar(
        select(func.count(Order.id)).where(
            Order.store_id == store.id,
            Order.current_status == OrderStatus.SEDANG_DIKEMAS.value
        )
    )
    
    siap_dikirim = await db.scalar(
        select(func.count(Order.id)).where(
            Order.store_id == store.id,
            Order.current_status == OrderStatus.MENUNGGU_PENGIRIM.value
        )
    )
    
    stok_kritis = await db.scalar(
        select(func.count(Product.id)).where(
            Product.store_id == store.id,
            Product.stock <= 5,
            Product.is_deleted == False
        )
    )
    
    # Chart Data (Last 7 Days)
    from datetime import timedelta, timezone
    from sqlalchemy import cast, Date
    
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    chart_result = await db.execute(
        select(
            cast(Order.created_at, Date).label('date'),
            func.sum(Order.final_total).label('revenue')
        )
        .where(
            Order.store_id == store.id, 
            Order.created_at >= seven_days_ago,
            Order.current_status == OrderStatus.PESANAN_SELESAI.value
        )
        .group_by(cast(Order.created_at, Date))
        .order_by(cast(Order.created_at, Date))
    )
    
    chart_data = []
    for row in chart_result.all():
        chart_data.append({
            "date": row.date.strftime('%Y-%m-%d'),
            "revenue": float(row.revenue)
        })
        
    # Low Stock Products (Max 5)
    low_stock_result = await db.execute(
        select(Product)
        .where(Product.store_id == store.id, Product.stock <= 5, Product.is_deleted == False)
        .order_by(Product.stock.asc())
        .limit(5)
    )
    low_stock_products = [
        {
            "id": str(p.id),
            "name": p.name,
            "price": float(p.price),
            "stock": p.stock
        } for p in low_stock_result.scalars().all()
    ]
    
    # Recent Orders (Queue) - showing latest 10
    orders_result = await db.execute(
        select(Order).where(Order.store_id == store.id).order_by(Order.created_at.desc()).limit(10)
    )
    orders = orders_result.scalars().all()
    
    return {
        "total_sales": float(total_sales or 0),
        "action_center": {
            "perlu_diproses": perlu_diproses or 0,
            "siap_dikirim": siap_dikirim or 0,
            "stok_kritis": stok_kritis or 0
        },
        "chart_data": chart_data,
        "low_stock_products": low_stock_products,
        "orders_queue": [
            {
                "id": str(o.id),
                "status": o.current_status,
                "total": float(o.final_total)
            } for o in orders
        ]
    }

# Driver Dashboard
@router.get("/driver/jobs/available")
async def get_driver_available_jobs(
    payload: dict = Depends(RequireActiveRole(["Driver"])),
    db: AsyncSession = Depends(get_db)
):
    # Find orders that need a driver
    orders_result = await db.execute(
        select(Order)
        .outerjoin(DeliveryJob, Order.id == DeliveryJob.order_id)
        .where(DeliveryJob.id == None)
        .where(Order.current_status.in_(['Menunggu Pengirim', 'Packed']))
    )
    orders = orders_result.scalars().all()
    
    return [
        {
            "order_id": str(o.id),
            "pickup": "Store Address (Pickup)",
            "dropoff": "Customer Address (Dropoff)",
            "fee": float(o.delivery_fee)
        } for o in orders
    ]
