from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.api.dependencies import RequireActiveRole, get_current_user_id
from app.models.user import User
from app.models.order import Order, DeliveryJob
from app.models.product import Product, Store
from datetime import datetime

router = APIRouter(tags=["Dashboards"])

# Admin Dashboard
@router.get("/admin/dashboard/stats")
async def get_admin_dashboard_stats(
    payload: dict = Depends(RequireActiveRole(["Admin"])),
    db: AsyncSession = Depends(get_db)
):
    users_count = await db.scalar(select(func.count(User.id)))
    stores_count = await db.scalar(select(func.count(Store.id)))
    products_count = await db.scalar(select(func.count(Product.id)))
    orders_count = await db.scalar(select(func.count(Order.id)))
    delivery_jobs_count = await db.scalar(select(func.count(DeliveryJob.id)))
    
    overdue_count = await db.scalar(
        select(func.count(Order.id)).where(Order.current_status == 'Overdue')
    )
    
    stmt = (
        select(Order, Store.store_name, User.full_name)
        .join(Store, Order.store_id == Store.id)
        .join(User, Order.buyer_id == User.id)
        .order_by(Order.created_at.desc())
        .limit(10)
    )
    result = await db.execute(stmt)
    
    recent_orders_data = []
    for order, store_name, buyer_name in result.all():
        recent_orders_data.append({
            "id": order.id,
            "store_name": store_name,
            "buyer_name": buyer_name,
            "current_status": order.current_status,
            "final_total": float(order.final_total),
            "created_at": order.created_at.isoformat() if order.created_at else datetime.utcnow().isoformat()
        })
    
    return {
        "users_count": users_count or 0,
        "stores_count": stores_count or 0,
        "products_count": products_count or 0,
        "orders_count": orders_count or 0,
        "delivery_jobs_count": delivery_jobs_count or 0,
        "overdue_orders_count": overdue_count or 0,
        "recent_orders": recent_orders_data,
        "simulated_date": datetime.utcnow().isoformat() + "Z"
    }

from pydantic import BaseModel

class SimulateNextDayRequest(BaseModel):
    days_forward: int = 1
    hours_forward: int = 0

# Admin Dashboard Simulation — Real Auto-Refund Engine
@router.post("/admin/simulate-next-day")
async def simulate_next_day(
    request: SimulateNextDayRequest,
    payload: dict = Depends(RequireActiveRole(["Admin"])),
    db: AsyncSession = Depends(get_db)
):
    from datetime import timedelta, timezone
    from sqlalchemy.orm import selectinload
    from app.schemas.order_schema import OrderStatus
    from app.models.order import OrderStatusHistory, OrderItem
    from app.models.wallet import Wallet, WalletTransaction
    from app.models.product import Product
    
    now = datetime.now(timezone.utc) + timedelta(days=request.days_forward, hours=request.hours_forward)
    
    # SLA thresholds per delivery method
    sla_hours = {
        "Instant": 4,
        "Next Day": 24,
        "Regular": 96,  # 4 days
    }
    
    # Find all active paid orders that haven't been completed or cancelled
    active_statuses = [
        OrderStatus.SEDANG_DIKEMAS.value,
        OrderStatus.MENUNGGU_PENGIRIM.value,
        OrderStatus.SEDANG_DIKIRIM.value
    ]
    
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.current_status.in_(active_statuses))
        .with_for_update()
    )
    active_orders = result.scalars().all()
    
    refunded_orders = []
    
    for order in active_orders:
        # Determine SLA deadline based on delivery method
        max_hours = sla_hours.get(order.delivery_method, 96)
        deadline = order.created_at.replace(tzinfo=timezone.utc) + timedelta(hours=max_hours)
        
        if now < deadline:
            continue  # Not overdue yet
        
        # === This order is OVERDUE — process auto-refund ===
        
        # 1. Update order status to "Dikembalikan"
        order.current_status = OrderStatus.DIKEMBALIKAN.value
        
        history = OrderStatusHistory(
            order_id=order.id,
            status_name=OrderStatus.DIKEMBALIKAN.value,
            changed_by_role="System"
        )
        db.add(history)
        
        # 2. Restore product stock
        if order.items:
            product_ids = [item.product_id for item in order.items]
            prod_result = await db.execute(
                select(Product).where(Product.id.in_(product_ids)).with_for_update()
            )
            products = {p.id: p for p in prod_result.scalars().all()}
            for item in order.items:
                prod = products.get(item.product_id)
                if prod:
                    prod.stock += item.quantity
        
        # 3. Refund buyer wallet
        wallet_result = await db.execute(
            select(Wallet).where(Wallet.buyer_id == order.buyer_id).with_for_update()
        )
        wallet = wallet_result.scalar_one_or_none()
        if wallet:
            wallet.balance += order.final_total
            txn = WalletTransaction(
                wallet_id=wallet.id,
                amount=order.final_total,
                transaction_type="Refund",
                reference_id=str(order.id),
                description=f"Auto-refund pesanan #{order.id} (overdue SLA)"
            )
            db.add(txn)
        
        refunded_orders.append({
            "order_id": order.id,
            "status": OrderStatus.DIKEMBALIKAN.value,
            "refund_amount": float(order.final_total)
        })
    
    await db.commit()
    
    return {
        "message": f"Simulasi selesai. {len(refunded_orders)} pesanan overdue telah di-refund.",
        "simulated_date": now.isoformat(),
        "refunded_orders": refunded_orders
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
