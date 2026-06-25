from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.db.session import get_db
from app.api.dependencies import get_token_payload, RequireActiveRole
from app.services.auth_service import get_user_roles
from app.models.user import User
from app.models.product import Product, Store
from app.models.review import ApplicationReview
from app.models.cart import Cart, CartItem
from app.models.order import Order, OrderItem
from app.models.promo import Promo, PromoProduct
from app.models.voucher import Voucher

from app.schemas.auth_schema import UserProfileResponse
from app.schemas.product_schema import ProductResponse
from app.schemas.review_schema import ReviewCreateRequest, ReviewResponse
from app.schemas.order_schema import CheckoutRequest, CheckoutResponse
from app.schemas.cart_schema import CartItemRequest, CartItemResponse, CartResponse
from app.schemas.address_schema import AddressRequest, AddressResponse
from app.schemas.promo_schema import PromoCreateRequest, PromoResponse, PromoUpdateRequest
from app.schemas.voucher_schema import VoucherCreateRequest, VoucherResponse, VoucherUpdateRequest, ValidateVoucherRequest, ValidateVoucherResponse
from decimal import Decimal
import uuid

router = APIRouter(tags=["Core App & Marketplace"])

@router.get("/users/me", response_model=UserProfileResponse)
async def get_me(
    payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db)
):
    user_id = payload.get("sub")
    active_role = payload.get("active_role")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    owned_roles = await get_user_roles(db, str(user.id))
    
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "roles": owned_roles,
        "active_role": active_role,
        "financials": {
            "walletBalance": 0.0,
            "sellerIncome": 0.0,
            "driverEarnings": 0.0
        }
    }

@router.get("/products", response_model=list[ProductResponse])
async def list_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.store), selectinload(Product.category))
        .where(Product.is_deleted == False)
    )
    products = result.scalars().all()
    
    response_list = []
    for product in products:
        image_url = None
        if product.images:
            primary_img = next((img for img in product.images if img.is_primary), None)
            if primary_img:
                image_url = primary_img.image_url
            else:
                image_url = product.images[0].image_url
                
        response_list.append({
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "promo_price": product.promo_price,
            "stock": product.stock,
            "image_url": image_url,
            "images": [img.image_url for img in product.images],
            "store_name": product.store.store_name if product.store else "SEAPEDIA Store",
            "category_name": product.category.name if product.category else "Unknown"
        })
        
    return response_list

@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.store), selectinload(Product.category))
        .where(Product.id == product_id, Product.is_deleted == False)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    image_url = None
    if product.images:
        primary_img = next((img for img in product.images if img.is_primary), None)
        if primary_img:
            image_url = primary_img.image_url
        else:
            image_url = product.images[0].image_url
            
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "promo_price": product.promo_price,
        "stock": product.stock,
        "image_url": image_url,
        "images": [img.image_url for img in product.images],
        "store_name": product.store.store_name if product.store else "SEAPEDIA Store",
        "category_name": product.category.name if product.category else "Unknown"
    }

@router.post("/reviews", response_model=dict)
async def create_review(request: ReviewCreateRequest, db: AsyncSession = Depends(get_db)):
    new_review = ApplicationReview(
        reviewer_name=request.reviewer_name,
        rating=request.rating,
        comment_text=request.comment
    )
    db.add(new_review)
    await db.commit()
    return {"message": "Review submitted successfully"}

@router.get("/reviews", response_model=list[ReviewResponse])
async def list_reviews(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ApplicationReview).order_by(ApplicationReview.created_at.desc()))
    reviews = result.scalars().all()
    
    return [
        {
            "id": str(review.id),
            "reviewer_name": review.reviewer_name,
            "rating": review.rating,
            "comment": review.comment_text,
            "created_at": review.created_at
        }
        for review in reviews
    ]

@router.get("/buyer/addresses", response_model=list[AddressResponse])
async def list_addresses(
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_id = uuid.UUID(user_id_str)
    
    from app.models.order import BuyerAddress
    result = await db.execute(select(BuyerAddress).where(BuyerAddress.buyer_id == user_id))
    addresses = result.scalars().all()
    
    return [
        {
            "id": addr.id,
            "buyer_id": str(addr.buyer_id),
            "full_address": addr.full_address
        }
        for addr in addresses
    ]

@router.post("/buyer/addresses", response_model=AddressResponse)
async def add_address(
    request: AddressRequest,
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_id = uuid.UUID(user_id_str)
    
    from app.models.order import BuyerAddress
    new_address = BuyerAddress(buyer_id=user_id, full_address=request.full_address)
    db.add(new_address)
    await db.commit()
    await db.refresh(new_address)
    
    return {
        "id": new_address.id,
        "buyer_id": str(new_address.buyer_id),
        "full_address": new_address.full_address
    }

@router.get("/buyer/cart", response_model=CartResponse)
async def get_cart(
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_id = uuid.UUID(user_id_str)
    
    result = await db.execute(
        select(Cart)
        .options(
            selectinload(Cart.items)
            .selectinload(CartItem.product)
            .selectinload(Product.images),
            selectinload(Cart.items)
            .selectinload(CartItem.product)
            .selectinload(Product.store)
        )
        .where(Cart.buyer_id == user_id)
    )
    cart = result.scalar_one_or_none()
    
    if not cart:
        return CartResponse(id=0, buyer_id=str(user_id), items=[], total_items=0, total_price=0)
        
    items_response = []
    total_items = 0
    total_price = Decimal('0.00')
    
    for item in cart.items:
        image_url = None
        if item.product.images:
            primary_img = next((img for img in item.product.images if img.is_primary), None)
            if primary_img:
                image_url = primary_img.image_url
            else:
                image_url = item.product.images[0].image_url
        
        store_name = item.product.store.store_name if item.product.store else f"Store #{item.product.store_id}"
        
        effective_price = item.product.promo_price if item.product.promo_price is not None else item.product.price

        items_response.append(CartItemResponse(
            id=item.id,
            product_id=item.product.id,
            product_name=item.product.name,
            product_image=image_url,
            store_id=item.product.store_id,
            store_name=store_name,
            quantity=item.quantity,
            unit_price=int(item.product.price),
            promo_price=int(item.product.promo_price) if item.product.promo_price is not None else None,
            total_price=int(effective_price * item.quantity)
        ))
        total_items += item.quantity
        total_price += effective_price * item.quantity
        
    return CartResponse(
        id=cart.id,
        buyer_id=str(cart.buyer_id),
        items=items_response,
        total_items=total_items,
        total_price=int(total_price)
    )

@router.post("/buyer/cart", response_model=CartResponse)
async def add_to_cart(
    request: CartItemRequest,
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_id = uuid.UUID(user_id_str)
    
    # Verify product exists
    prod_result = await db.execute(select(Product).where(Product.id == request.product_id, Product.is_deleted == False))
    product = prod_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    
    # (Old stock check removed as it's handled below)
    # Get or create cart
    result = await db.execute(
        select(Cart)
        .options(selectinload(Cart.items))
        .where(Cart.buyer_id == user_id)
        .with_for_update()
    )
    cart = result.scalar_one_or_none()
    
    if not cart:
        cart = Cart(buyer_id=user_id)
        db.add(cart)
        await db.flush()
        cart_items = []
    else:
        cart_items = cart.items
            
    # Check if item already exists in cart (no single-store constraint)
    existing_item = next((i for i in cart_items if i.product_id == request.product_id), None)
    
    new_total_quantity = (existing_item.quantity if existing_item else 0) + request.quantity
    
    if new_total_quantity > 0 and product.stock < new_total_quantity:
        raise HTTPException(status_code=400, detail=f"Stok tidak cukup untuk {product.name}. Tersisa {product.stock} unit.")
    
    if existing_item:
        if new_total_quantity <= 0:
            if existing_item in cart.items:
                cart.items.remove(existing_item)
            await db.delete(existing_item)
        else:
            existing_item.quantity = new_total_quantity
    else:
        if request.quantity > 0:
            new_item = CartItem(cart_id=cart.id, product_id=request.product_id, quantity=request.quantity)
            db.add(new_item)
        
    await db.commit()
    
    # Fetch full updated cart for response
    return await get_cart(payload=payload, db=db)

@router.post("/buyer/checkout/validate-voucher", response_model=ValidateVoucherResponse)
async def validate_voucher(
    request: ValidateVoucherRequest,
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    if not request.voucher_code:
        raise HTTPException(status_code=400, detail="Kode voucher tidak boleh kosong.")
        
    voucher_result = await db.execute(
        select(Voucher).where(
            Voucher.code == request.voucher_code.strip().upper(),
            Voucher.is_deleted == False
        )
    )
    voucher = voucher_result.scalar_one_or_none()
    
    if not voucher:
        raise HTTPException(status_code=400, detail="Kode voucher tidak valid atau sudah tidak berlaku.")
        
    from datetime import datetime, timezone
    if voucher.valid_until and voucher.valid_until.replace(tzinfo=None) < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Kode voucher sudah kedaluwarsa.")
    if voucher.valid_from and voucher.valid_from.replace(tzinfo=None) > datetime.utcnow():
        raise HTTPException(status_code=400, detail="Kode voucher belum mulai berlaku.")
        
    if voucher.remaining_usage is not None and voucher.remaining_usage <= 0:
        raise HTTPException(status_code=400, detail="Kuota pemakaian kode voucher sudah habis.")
        
    if request.subtotal < voucher.min_purchase:
         raise HTTPException(status_code=400, detail=f"Minimal belanja untuk voucher ini adalah Rp {voucher.min_purchase}")

    discount_amount = Decimal('0.00')
    if voucher.discount_type.upper() == 'PERCENTAGE':
        discount_amount = (request.subtotal * voucher.amount / Decimal('100')).quantize(Decimal('0.01'))
        if voucher.max_discount and discount_amount > voucher.max_discount:
             discount_amount = voucher.max_discount
    else:
        discount_amount = voucher.amount
        
    if discount_amount > request.subtotal:
        discount_amount = request.subtotal
        
    return ValidateVoucherResponse(
        is_valid=True,
        code=voucher.code,
        amount=discount_amount,
        message="Voucher berhasil digunakan."
    )

@router.post("/buyer/checkout", response_model=CheckoutResponse)
async def checkout(
    request: CheckoutRequest,
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_id = uuid.UUID(user_id_str)
    
    if not request.cart_item_ids:
        raise HTTPException(status_code=400, detail="Tidak ada barang yang dipilih untuk dicheckout.")
        
    # 1. Fetch Cart
    result = await db.execute(
        select(Cart)
        .options(selectinload(Cart.items).selectinload(CartItem.product))
        .where(Cart.buyer_id == user_id)
    )
    cart = result.scalar_one_or_none()
    
    if not cart or not cart.items:
        raise HTTPException(status_code=400, detail="Keranjang kosong.")
        
    # Verify Address exists
    from app.models.order import BuyerAddress
    addr_res = await db.execute(select(BuyerAddress).where(BuyerAddress.id == request.address_id, BuyerAddress.buyer_id == user_id))
    address = addr_res.scalar_one_or_none()
    if not address:
        # Auto-create dummy address to prevent foreign key violation if frontend hardcoded 1
        dummy_address = BuyerAddress(buyer_id=user_id, full_address="Alamat Default Otomatis")
        db.add(dummy_address)
        await db.flush()
        request.address_id = dummy_address.id
        
    # Filter items that are actually in the request
    selected_items = [item for item in cart.items if item.id in request.cart_item_ids]
    if not selected_items:
        raise HTTPException(status_code=400, detail="Barang yang dipilih tidak ditemukan di keranjang.")
    if len(selected_items) != len(request.cart_item_ids):
        raise HTTPException(status_code=400, detail="Beberapa barang yang dipilih tidak valid.")
        
    # 2. Validate Single-Store Constraint
    store_ids = {item.product.store_id for item in selected_items}
    if len(store_ids) > 1:
        raise HTTPException(
            status_code=400,
            detail="Checkout hanya dapat dilakukan untuk produk dari satu toko. Silakan pilih barang dari toko yang sama."
        )
    store_id = list(store_ids)[0]
    
    # 3. Lock Products for Race Condition (SELECT ... FOR UPDATE)
    product_ids = [item.product_id for item in selected_items]
    prod_result = await db.execute(
        select(Product)
        .options(selectinload(Product.promo_products).selectinload(PromoProduct.promo))
        .where(Product.id.in_(product_ids))
        .with_for_update()
    )
    products_locked = {p.id: p for p in prod_result.scalars().all()}
    
    subtotal = Decimal('0.00')
    promo_discount_amount = Decimal('0.00')
    promo_id = None # Assuming we just take the first promo found for logging if needed, or we might need a mapping. Since Order currently has only one promo_id, we will store the last used promo_id or null if multiple.
    
    from datetime import datetime, timezone
    now = datetime.utcnow()

    # To track the applied prices
    item_applied_prices = {}

    for item in selected_items:
        locked_product = products_locked.get(item.product_id)
        if not locked_product:
            raise HTTPException(status_code=400, detail=f"Produk {item.product_id} tidak ditemukan.")
        if locked_product.stock < item.quantity:
            raise HTTPException(status_code=400, detail=f"Stok tidak cukup untuk {locked_product.name}. Tersisa {locked_product.stock} unit.")
        
        # Deduct stock
        locked_product.stock -= item.quantity
        
        base_price = locked_product.price
        subtotal += base_price * item.quantity
        
        # Calculate promo
        item_promo_discount = Decimal('0.00')
        if locked_product.promo_products:
            for pp in locked_product.promo_products:
                promo = pp.promo
                if promo.is_active and promo.valid_from.replace(tzinfo=None) <= now <= promo.valid_until.replace(tzinfo=None):
                    # Found an active promo
                    item_promo_discount = (base_price * promo.discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
                    promo_id = promo.id # Just store the last applied promo ID for the order
                    break
                    
        promo_discount_amount += item_promo_discount * item.quantity
        item_applied_prices[item.product_id] = base_price - item_promo_discount
        
    # 4. Calculate Voucher Discount
    voucher_discount_amount = Decimal('0.00')
    voucher_id = None
    subtotal_after_promo = subtotal - promo_discount_amount
    
    if request.voucher_code:
        voucher_result = await db.execute(
            select(Voucher).where(
                Voucher.code == request.voucher_code.strip().upper(),
                Voucher.is_deleted == False
            ).with_for_update()
        )
        voucher = voucher_result.scalar_one_or_none()
        if not voucher:
            raise HTTPException(status_code=400, detail="Kode voucher tidak valid atau sudah tidak berlaku.")
        
        # Validate expiry
        if voucher.valid_until and voucher.valid_until.replace(tzinfo=None) < now:
            raise HTTPException(status_code=400, detail="Kode voucher sudah kedaluwarsa.")
        if voucher.valid_from and voucher.valid_from.replace(tzinfo=None) > now:
            raise HTTPException(status_code=400, detail="Kode voucher belum mulai berlaku.")
            
        # Validate minimum purchase against subtotal AFTER promo
        if subtotal_after_promo < voucher.min_purchase:
             raise HTTPException(status_code=400, detail=f"Minimal belanja untuk voucher ini adalah Rp {voucher.min_purchase}")
        
        # Validate remaining usage
        if voucher.remaining_usage is not None and voucher.remaining_usage <= 0:
            raise HTTPException(status_code=400, detail="Kuota pemakaian kode voucher sudah habis.")
        
        # Calculate based on discount type
        if voucher.discount_type.upper() == 'PERCENTAGE':
            voucher_discount_amount = (subtotal_after_promo * voucher.amount / Decimal('100')).quantize(Decimal('0.01'))
            if voucher.max_discount and voucher_discount_amount > voucher.max_discount:
                 voucher_discount_amount = voucher.max_discount
        else:
            voucher_discount_amount = voucher.amount
        
        # Cap discount to subtotal after promo
        if voucher_discount_amount > subtotal_after_promo:
            voucher_discount_amount = subtotal_after_promo
        
        voucher_id = voucher.id
        
        # Decrement usage
        if voucher.remaining_usage is not None:
            voucher.remaining_usage -= 1
        
    # 5. Delivery Fee
    req_delivery = request.delivery_method.upper()
    delivery_fees = {
        "INSTANT": Decimal('20000.00'),
        "NEXT_DAY": Decimal('15000.00'),
        "REGULAR": Decimal('10000.00')
    }
    
    db_delivery_mapping = {
        "INSTANT": "Instant",
        "NEXT_DAY": "Next Day",
        "REGULAR": "Regular"
    }
    
    delivery_fee = delivery_fees.get(req_delivery, Decimal('10000.00'))
    db_delivery_method = db_delivery_mapping.get(req_delivery, "Regular")
    
    # 6. PPN 12%
    ppn_amount = ((subtotal - promo_discount_amount - voucher_discount_amount) * Decimal('0.12')).quantize(Decimal('0.01'))
    if ppn_amount < 0:
        ppn_amount = Decimal('0.00')
        
    final_total = subtotal - promo_discount_amount - voucher_discount_amount + delivery_fee + ppn_amount
    if final_total < 0:
        final_total = Decimal('0.00')
        
    # 7. Create Order
    new_order = Order(
        buyer_id=user_id,
        store_id=store_id,
        address_id=request.address_id,
        promo_id=promo_id,
        voucher_id=voucher_id,
        delivery_method=db_delivery_method,
        subtotal=subtotal,
        promo_discount_amount=promo_discount_amount,
        voucher_discount_amount=voucher_discount_amount,
        delivery_fee=delivery_fee,
        ppn_amount=ppn_amount,
        final_total=final_total,
        current_status=OrderStatus.MENUNGGU_PEMBAYARAN.value
    )
    db.add(new_order)
    await db.flush() # To get new_order.id
    
    # 7.5 Create Initial Order History
    history = OrderStatusHistory(
        order_id=new_order.id,
        status_name=OrderStatus.MENUNGGU_PEMBAYARAN.value,
        changed_by_user_id=user_id,
        changed_by_role="Buyer"
    )
    db.add(history)
    
    
    # 8. Create Order Items
    for item in selected_items:
        effective_price = item_applied_prices[item.product_id]
        order_item = OrderItem(
            order_id=new_order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price_at_purchase=effective_price
        )
        db.add(order_item)
        
    # 9. Clear Selected Cart Items
    for item in selected_items:
        await db.delete(item)
        
    await db.commit()
        
    return CheckoutResponse(
        order_id=new_order.id,
        subtotal=subtotal,
        promo_discount_amount=promo_discount_amount,
        voucher_discount_amount=voucher_discount_amount,
        delivery_fee=delivery_fee,
        ppn_amount=ppn_amount,
        final_total=final_total,
        message="Checkout berhasil!"
    )

@router.post("/buyer/orders/{order_id}/pay")
async def pay_order(
    order_id: int,
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_id = uuid.UUID(user_id_str)
    
    # Fetch Order
    order_res = await db.execute(
        select(Order)
        .where(Order.id == order_id, Order.buyer_id == user_id)
        .with_for_update()
    )
    order = order_res.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan.")
        
    if order.current_status != OrderStatus.MENUNGGU_PEMBAYARAN.value:
        raise HTTPException(status_code=400, detail="Pesanan tidak dalam status Menunggu Pembayaran.")
        
    # Fetch Wallet
    from app.models.wallet import Wallet, WalletTransaction
    wallet_res = await db.execute(
        select(Wallet)
        .where(Wallet.buyer_id == user_id)
        .with_for_update()
    )
    wallet = wallet_res.scalar_one_or_none()
    
    if not wallet or wallet.balance < order.final_total:
        raise HTTPException(status_code=400, detail="Saldo dompet tidak mencukupi, silakan Top-Up terlebih dahulu.")
        
    # Deduct Wallet
    wallet.balance -= order.final_total
    txn = WalletTransaction(
        wallet_id=wallet.id,
        amount=-order.final_total,
        transaction_type="Payment",
        reference_id=str(order.id),
        description=f"Pembayaran pesanan #{order.id}"
    )
    db.add(txn)
    
    # Update Order
    order.current_status = OrderStatus.SEDANG_DIKEMAS.value
    
    history = OrderStatusHistory(
        order_id=order.id,
        status_name=OrderStatus.SEDANG_DIKEMAS.value,
        changed_by_user_id=user_id,
        changed_by_role="Buyer"
    )
    db.add(history)
    
    await db.commit()
    
    return {"message": "Pembayaran berhasil, pesanan sedang diproses."}



# --- Order Tracking & Delivery Endpoints ---

from app.schemas.order_schema import OrderStatusUpdateRequest, OrderStatusHistoryResponse, OrderStatus
from app.models.order import OrderStatusHistory, DeliveryJob

@router.get("/orders/{order_id}/tracking", response_model=list[OrderStatusHistoryResponse])
async def get_order_tracking(
    order_id: int,
    payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db)
):
    # Retrieve history
    result = await db.execute(
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order_id)
        .order_by(OrderStatusHistory.created_at.asc())
    )
    history = result.scalars().all()
    
    return [
        OrderStatusHistoryResponse(
            id=h.id,
            status_name=h.status_name,
            changed_by_user_id=str(h.changed_by_user_id) if h.changed_by_user_id else None,
            changed_by_role=h.changed_by_role,
            created_at=h.created_at
        ) for h in history
    ]

@router.patch("/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    request: OrderStatusUpdateRequest,
    payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        user_id = uuid.UUID(user_id_str)
        active_role = payload.get("active_role")
        
        if active_role != "SELLER":
            raise HTTPException(status_code=403, detail="Hanya Seller yang dapat memproses pesanan melalui endpoint ini")
            
        # Get order with lock
        result = await db.execute(select(Order).where(Order.id == order_id).with_for_update())
        order = result.scalar_one_or_none()
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
            
        # Verify Seller ownership
        store_result = await db.execute(select(Store).where(Store.seller_id == user_id))
        store = store_result.scalar_one_or_none()
        if not store or order.store_id != store.id:
            raise HTTPException(status_code=403, detail="Anda tidak memiliki akses ke pesanan ini")

        # State transition validation
        if order.current_status != OrderStatus.SEDANG_DIKEMAS.value:
            raise HTTPException(status_code=400, detail=f"Pesanan dengan status '{order.current_status}' tidak dapat diproses")
            
        if request.status != OrderStatus.MENUNGGU_PENGIRIM.value:
            raise HTTPException(status_code=400, detail="Seller hanya dapat mengubah status menjadi Menunggu Pengirim")
            
        order.current_status = request.status.value
        
        history = OrderStatusHistory(
            order_id=order.id,
            status_name=request.status.value,
            changed_by_user_id=user_id,
            changed_by_role=active_role
        )
        db.add(history)
        await db.commit()
        
        return {"message": "Status updated successfully", "new_status": request.status.value}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/driver/deliveries/{order_id}/take")
async def take_delivery_job(
    order_id: int,
    payload: dict = Depends(RequireActiveRole(["DRIVER", "Driver"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_id = uuid.UUID(user_id_str)
    
    # Use explicit FOR UPDATE to avoid race condition
    result = await db.execute(select(Order).where(Order.id == order_id).with_for_update())
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if order.current_status != OrderStatus.MENUNGGU_PENGIRIM.value:
        raise HTTPException(status_code=400, detail="Order is not available for pickup")
        
    # Check if a delivery job already exists
    job_result = await db.execute(select(DeliveryJob).where(DeliveryJob.order_id == order_id))
    if job_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Job already taken by another driver")
        
    # Assign job
    new_job = DeliveryJob(
        order_id=order.id,
        driver_id=user_id,
        driver_earning=order.delivery_fee,
        status=OrderStatus.SEDANG_DIKIRIM.value
    )
    db.add(new_job)
    
    # Update order status
    order.current_status = OrderStatus.SEDANG_DIKIRIM.value
    
    # Add history
    history = OrderStatusHistory(
        order_id=order.id,
        status_name=OrderStatus.SEDANG_DIKIRIM.value,
        changed_by_user_id=user_id,
        changed_by_role="Driver"
    )
    db.add(history)
    
    await db.commit()
    
    return {"message": "Delivery job taken successfully"}

@router.post("/driver/deliveries/{order_id}/complete")
async def complete_delivery_job(
    order_id: int,
    payload: dict = Depends(RequireActiveRole(["DRIVER", "Driver"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_id = uuid.UUID(user_id_str)
    
    # Fetch job and order
    job_result = await db.execute(select(DeliveryJob).where(DeliveryJob.order_id == order_id).with_for_update())
    job = job_result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Delivery job not found")
        
    if job.driver_id != user_id:
        raise HTTPException(status_code=403, detail="You are not authorized to complete this job")
        
    order_result = await db.execute(select(Order).where(Order.id == order_id).with_for_update())
    order = order_result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if order.current_status != OrderStatus.SEDANG_DIKIRIM.value:
        raise HTTPException(status_code=400, detail="Pesanan ini tidak sedang dalam pengiriman")

    from datetime import datetime, timezone
    job.status = OrderStatus.PESANAN_SELESAI.value
    job.completed_at = datetime.now(timezone.utc)
    
    order.current_status = OrderStatus.PESANAN_SELESAI.value
    
    history = OrderStatusHistory(
        order_id=order.id,
        status_name=OrderStatus.PESANAN_SELESAI.value,
        changed_by_user_id=user_id,
        changed_by_role="Driver"
    )
    db.add(history)
    
    await db.commit()
    
    return {"message": "Delivery job completed successfully"}

from app.schemas.order_schema import OrderResponse, OrderItemResponse

@router.get("/driver/jobs/available", response_model=list[OrderResponse])
async def get_available_delivery_jobs(
    payload: dict = Depends(RequireActiveRole(["DRIVER", "Driver"])),
    db: AsyncSession = Depends(get_db)
):
    query = (
        select(Order)
        .options(
            selectinload(Order.store),
            selectinload(Order.address),
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images)
        )
        .where(Order.current_status == OrderStatus.MENUNGGU_PENGIRIM.value)
        .order_by(Order.created_at.asc())
    )
    result = await db.execute(query)
    orders = result.scalars().all()
    
    response_list = []
    for order in orders:
        items_resp = []
        for item in order.items:
            img_url = None
            if item.product and item.product.images:
                primary_img = next((img for img in item.product.images if img.is_primary), None)
                img_url = primary_img.image_url if primary_img else item.product.images[0].image_url
                
            items_resp.append(OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else "Unknown Product",
                quantity=item.quantity,
                unit_price=item.unit_price_at_purchase,
                product_image=img_url
            ))
            
        response_list.append(OrderResponse(
            id=order.id,
            store_name=order.store.store_name if order.store else "Unknown Store",
            current_status=order.current_status,
            final_total=order.final_total,
            delivery_fee=order.delivery_fee,
            shipping_address=order.address.full_address if order.address else None,
            created_at=order.created_at,
            items=items_resp
        ))
    return response_list

@router.get("/driver/jobs/active", response_model=list[OrderResponse])
async def get_active_delivery_jobs(
    payload: dict = Depends(RequireActiveRole(["DRIVER", "Driver"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_uuid = uuid.UUID(user_id_str)
    
    query = (
        select(Order)
        .join(DeliveryJob, Order.id == DeliveryJob.order_id)
        .options(
            selectinload(Order.store),
            selectinload(Order.address),
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images)
        )
        .where(
            DeliveryJob.driver_id == user_uuid,
            DeliveryJob.status == OrderStatus.SEDANG_DIKIRIM.value,
            Order.current_status == OrderStatus.SEDANG_DIKIRIM.value
        )
        .order_by(DeliveryJob.taken_at.desc())
    )
    result = await db.execute(query)
    orders = result.scalars().all()
    
    response_list = []
    for order in orders:
        items_resp = []
        for item in order.items:
            img_url = None
            if item.product and item.product.images:
                primary_img = next((img for img in item.product.images if img.is_primary), None)
                img_url = primary_img.image_url if primary_img else item.product.images[0].image_url
                
            items_resp.append(OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else "Unknown Product",
                quantity=item.quantity,
                unit_price=item.unit_price_at_purchase,
                product_image=img_url
            ))
            
        response_list.append(OrderResponse(
            id=order.id,
            store_name=order.store.store_name if order.store else "Unknown Store",
            current_status=order.current_status,
            final_total=order.final_total,
            delivery_fee=order.delivery_fee,
            shipping_address=order.address.full_address if order.address else None,
            created_at=order.created_at,
            items=items_resp
        ))
    return response_list

@router.get("/driver/earnings")
async def get_driver_earnings(
    payload: dict = Depends(RequireActiveRole(["DRIVER", "Driver"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_uuid = uuid.UUID(user_id_str)
    
    total = await db.scalar(
        select(func.sum(DeliveryJob.driver_earning)).where(
            DeliveryJob.driver_id == user_uuid,
            DeliveryJob.status == OrderStatus.PESANAN_SELESAI.value
        )
    )
    
    jobs_result = await db.execute(
        select(DeliveryJob, Order).join(Order, DeliveryJob.order_id == Order.id)
        .where(
            DeliveryJob.driver_id == user_uuid,
            DeliveryJob.status == OrderStatus.PESANAN_SELESAI.value
        )
        .order_by(DeliveryJob.completed_at.desc())
    )
    
    history = []
    for job, order in jobs_result.all():
        history.append({
            "job_id": job.id,
            "order_id": order.id,
            "earning": float(job.driver_earning),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None
        })
        
    return {
        "total_earnings": float(total) if total else 0,
        "history": history
    }

# --- Buyer Endpoints ---

@router.get("/buyer/orders", response_model=list[OrderResponse])
async def get_buyer_orders(
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_id = uuid.UUID(user_id_str)
    
    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.store),
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images)
        )
        .where(Order.buyer_id == user_id)
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()
    
    response_list = []
    for order in orders:
        items_resp = []
        for item in order.items:
            img_url = None
            if item.product and item.product.images:
                primary_img = next((img for img in item.product.images if img.is_primary), None)
                img_url = primary_img.image_url if primary_img else item.product.images[0].image_url
                
            items_resp.append(OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else "Unknown Product",
                quantity=item.quantity,
                unit_price=item.unit_price_at_purchase,
                product_image=img_url
            ))
            
        response_list.append(OrderResponse(
            id=order.id,
            store_name=order.store.store_name if order.store else "Unknown Store",
            current_status=order.current_status,
            final_total=order.final_total,
            delivery_fee=order.delivery_fee,
            created_at=order.created_at,
            items=items_resp
        ))
        
    return response_list

@router.get("/buyer/orders/{order_id}", response_model=OrderResponse)
async def get_buyer_order_detail(
    order_id: int,
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_id = uuid.UUID(user_id_str)
    
    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.store),
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images)
        )
        .where(Order.id == order_id, Order.buyer_id == user_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    items_resp = []
    for item in order.items:
        img_url = None
        if item.product and item.product.images:
            primary_img = next((img for img in item.product.images if img.is_primary), None)
            img_url = primary_img.image_url if primary_img else item.product.images[0].image_url
            
        items_resp.append(OrderItemResponse(
            id=item.id,
            product_id=item.product_id,
            product_name=item.product.name if item.product else "Unknown Product",
            quantity=item.quantity,
            unit_price=item.unit_price_at_purchase,
            product_image=img_url
        ))
        
    return OrderResponse(
        id=order.id,
        store_name=order.store.store_name if order.store else "Unknown Store",
        current_status=order.current_status,
        final_total=order.final_total,
        delivery_fee=order.delivery_fee,
        created_at=order.created_at,
        items=items_resp
    )

@router.post("/buyer/orders/{order_id}/cancel")
async def cancel_order_buyer(
    order_id: int,
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    user_uuid = uuid.UUID(user_id_str)
    
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items))
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if order.buyer_id != user_uuid:
        raise HTTPException(status_code=403, detail="Not your order")
        
    from app.schemas.order_schema import OrderStatus
    if order.current_status not in [OrderStatus.MENUNGGU_PEMBAYARAN.value, OrderStatus.SEDANG_DIKEMAS.value]:
        raise HTTPException(status_code=400, detail="Pesanan sudah diproses dan tidak dapat dibatalkan")
        
    is_paid = (order.current_status == OrderStatus.SEDANG_DIKEMAS.value)
    order.current_status = OrderStatus.DIBATALKAN.value
    
    # Return stock
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
                
    # Refund wallet if paid
    if is_paid:
        from app.models.wallet import Wallet, WalletTransaction
        wallet_res = await db.execute(
            select(Wallet).where(Wallet.buyer_id == user_uuid).with_for_update()
        )
        wallet = wallet_res.scalar_one_or_none()
        if wallet:
            wallet.balance += order.final_total
            txn = WalletTransaction(
                wallet_id=wallet.id,
                amount=order.final_total,
                transaction_type="Refund",
                reference_id=str(order.id),
                description=f"Refund pembatalan pesanan #{order.id}"
            )
            db.add(txn)
    
    # record history
    history = OrderStatusHistory(
        order_id=order.id,
        status_name=OrderStatus.DIBATALKAN.value,
        changed_by_user_id=user_uuid,
        changed_by_role="Buyer"
    )
    db.add(history)
    await db.commit()
    return {"message": "Pesanan berhasil dibatalkan."}

# --- Seller Endpoints ---

from app.schemas.store_schema import StoreCreateRequest, StoreStatusResponse, StoreResponse
from app.api.dependencies import get_current_user_id

@router.get("/seller/store/status", response_model=StoreStatusResponse)
async def get_seller_store_status(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Store).where(Store.seller_id == uuid.UUID(user_id)))
    store = result.scalar_one_or_none()
    
    if store:
        return StoreStatusResponse(has_store=True, store_name=store.store_name, store_id=store.id)
    return StoreStatusResponse(has_store=False)

@router.post("/seller/store", response_model=StoreResponse, status_code=201)
async def create_seller_store(
    request: StoreCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    user_uuid = uuid.UUID(user_id)
    
    # Check if user already has a store
    existing_store = await db.execute(select(Store).where(Store.seller_id == user_uuid))
    if existing_store.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Anda sudah memiliki toko.")
        
    # Check if store_name is unique
    existing_name = await db.execute(select(Store).where(Store.store_name == request.store_name))
    if existing_name.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Nama toko ini sudah digunakan oleh pengguna lain. Silakan pilih nama lain.")
        
    new_store = Store(
        seller_id=user_uuid,
        store_name=request.store_name
    )
    db.add(new_store)
    await db.commit()
    await db.refresh(new_store)
    
    return new_store

@router.get("/seller/orders/incoming", response_model=list[OrderResponse])
async def get_incoming_seller_orders(
    status: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    payload: dict = Depends(RequireActiveRole(["SELLER"])),
    db: AsyncSession = Depends(get_db)
):
    user_uuid = uuid.UUID(user_id)
    
    # Get user's store
    store_result = await db.execute(select(Store).where(Store.seller_id == user_uuid))
    store = store_result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan.")
        
    query = (
        select(Order)
        .options(
            selectinload(Order.store),
            selectinload(Order.address),
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images)
        )
        .where(Order.store_id == store.id)
    )
    
    if status:
        if status == "Dikembalikan":
            from app.schemas.order_schema import OrderStatus
            query = query.where(Order.current_status.in_([OrderStatus.DIKEMBALIKAN.value, OrderStatus.DIBATALKAN.value]))
        else:
            query = query.where(Order.current_status == status)
    else:
        # Exclude "Menunggu Pembayaran"
        from app.schemas.order_schema import OrderStatus
        query = query.where(Order.current_status != OrderStatus.MENUNGGU_PEMBAYARAN.value)
        
    result = await db.execute(query.order_by(Order.created_at.desc()))
    orders = result.scalars().all()
    
    response_list = []
    for order in orders:
        items_resp = []
        for item in order.items:
            img_url = None
            if item.product and item.product.images:
                primary_img = next((img for img in item.product.images if img.is_primary), None)
                img_url = primary_img.image_url if primary_img else item.product.images[0].image_url
                
            items_resp.append(OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else "Unknown Product",
                quantity=item.quantity,
                unit_price=item.unit_price_at_purchase,
                product_image=img_url
            ))
            
        response_list.append(OrderResponse(
            id=order.id,
            store_name=order.store.store_name if order.store else "Unknown Store",
            current_status=order.current_status,
            final_total=order.final_total,
            delivery_fee=order.delivery_fee,
            shipping_address=order.address.full_address if order.address else None,
            created_at=order.created_at,
            items=items_resp
        ))
        
    return response_list

# --- Seller Product Management Endpoints ---

from app.schemas.seller_schema import ProductCreateRequest, SellerProductResponse, CategoryResponse, ProductUpdateRequest
from app.models.product import Category, ProductImage

@router.get("/categories", response_model=list[CategoryResponse])
async def get_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.name))
    return result.scalars().all()

@router.get("/seller/products", response_model=list[SellerProductResponse])
async def get_seller_products(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    user_uuid = uuid.UUID(user_id)
    store_result = await db.execute(select(Store).where(Store.seller_id == user_uuid))
    store = store_result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan.")

    result = await db.execute(
        select(Product)
        .options(selectinload(Product.category), selectinload(Product.images))
        .where(Product.store_id == store.id)
        .order_by(Product.created_at.desc())
    )
    products = result.scalars().all()

    return [
        SellerProductResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            price=p.price,
            promo_price=p.promo_price,
            stock=p.stock,
            category_name=p.category.name if p.category else "Uncategorized",
            image_url=next((img.image_url for img in p.images if img.is_primary), p.images[0].image_url if p.images else None),
            is_deleted=p.is_deleted
        ) for p in products
    ]

from fastapi import File, UploadFile
from supabase import create_client, Client

@router.post("/seller/products/image")
async def upload_product_image(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id)
):
    """
    Upload a product image to Supabase Storage and return the public URL.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase is not configured on the backend.")
        
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
        
    if file.size and file.size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB")

    # Read file content
    content = await file.read()
    
    # Generate unique filename
    import uuid
    import time
    ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
    file_name = f"{uuid.uuid4()}_{int(time.time())}.{ext}"
    
    try:
        supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        bucket_name = "product-images"
        
        # Upload
        res = supabase.storage.from_(bucket_name).upload(
            path=file_name,
            file=content,
            file_options={"content-type": file.content_type}
        )
        
        # Get public url
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
        
        return {"url": public_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to storage: {str(e)}")

@router.post("/seller/products", response_model=SellerProductResponse, status_code=201)
async def create_seller_product(
    request: ProductCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    user_uuid = uuid.UUID(user_id)
    store_result = await db.execute(select(Store).where(Store.seller_id == user_uuid))
    store = store_result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Anda belum memiliki toko.")

    # Validate category exists
    cat_result = await db.execute(select(Category).where(Category.id == request.category_id))
    category = cat_result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=400, detail="Kategori tidak ditemukan.")

    new_product = Product(
        store_id=store.id,
        category_id=request.category_id,
        name=request.name,
        description=request.description,
        price=request.price,
        promo_price=request.promo_price,
        stock=request.stock
    )
    db.add(new_product)
    await db.flush() # flush to get new_product.id
    
    # Save image_url if provided
    if request.image_url:
        new_image = ProductImage(
            product_id=new_product.id,
            image_url=request.image_url,
            is_primary=True
        )
        db.add(new_image)
        
    await db.commit()
    await db.refresh(new_product)
    
    # Explicitly load relationships to return a complete response
    await db.refresh(new_product, ["category", "images"])
    return SellerProductResponse(
        id=new_product.id,
        name=new_product.name,
        description=new_product.description,
        price=new_product.price,
        promo_price=new_product.promo_price,
        stock=new_product.stock,
        category_name=category.name,
        image_url=request.image_url,
        is_deleted=new_product.is_deleted
    )

@router.put("/seller/products/{product_id}", response_model=SellerProductResponse)
async def update_seller_product(
    product_id: int,
    request: ProductUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    user_uuid = uuid.UUID(user_id)
    store_result = await db.execute(select(Store).where(Store.seller_id == user_uuid))
    store = store_result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Anda belum memiliki toko.")

    # Get product
    prod_result = await db.execute(
        select(Product)
        .options(selectinload(Product.category), selectinload(Product.images))
        .where(Product.id == product_id, Product.store_id == store.id, Product.is_deleted == False)
    )
    product = prod_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan atau sudah dihapus.")

    # Validate category
    cat_result = await db.execute(select(Category).where(Category.id == request.category_id))
    category = cat_result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=400, detail="Kategori tidak ditemukan.")

    # Update product
    product.name = request.name
    product.description = request.description
    product.price = request.price
    product.promo_price = request.promo_price
    product.stock = request.stock
    product.category_id = request.category_id

    await db.commit()
    await db.refresh(product)

    return SellerProductResponse(
        id=product.id,
        name=product.name,
        description=product.description,
        price=product.price,
        promo_price=product.promo_price,
        stock=product.stock,
        category_name=category.name,
        image_url=next((img.image_url for img in product.images if img.is_primary), product.images[0].image_url if product.images else None),
        is_deleted=product.is_deleted
    )

@router.delete("/seller/products/{product_id}", status_code=204)
async def delete_seller_product(
    product_id: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    user_uuid = uuid.UUID(user_id)
    store_result = await db.execute(select(Store).where(Store.seller_id == user_uuid))
    store = store_result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Anda belum memiliki toko.")

    # Get product
    prod_result = await db.execute(
        select(Product).where(Product.id == product_id, Product.store_id == store.id, Product.is_deleted == False)
    )
    product = prod_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")

    # Soft delete
    product.is_deleted = True
    await db.commit()
    return None

# --- Buyer Wallet & Address Endpoints ---

from app.models.wallet import Wallet, WalletTransaction
from app.schemas.wallet_schema import WalletResponse, WalletTransactionResponse, TopUpRequest
from app.models.order import BuyerAddress

@router.get("/buyer/wallet", response_model=WalletResponse)
async def get_buyer_wallet(
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id = uuid.UUID(payload.get("sub"))
    result = await db.execute(
        select(Wallet)
        .options(selectinload(Wallet.transactions))
        .where(Wallet.buyer_id == user_id)
    )
    wallet = result.scalar_one_or_none()

    if not wallet:
        # Auto-create wallet for buyer
        wallet = Wallet(buyer_id=user_id)
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)
        return WalletResponse(id=wallet.id, balance=wallet.balance, transactions=[])

    txns = sorted(wallet.transactions, key=lambda t: t.created_at, reverse=True)[:20]
    return WalletResponse(
        id=wallet.id,
        balance=wallet.balance,
        transactions=[
            WalletTransactionResponse(
                id=t.id, amount=t.amount, transaction_type=t.transaction_type,
                description=t.description, created_at=t.created_at
            ) for t in txns
        ]
    )

@router.post("/buyer/wallet/topup", response_model=WalletResponse)
async def topup_buyer_wallet(
    request: TopUpRequest,
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id = uuid.UUID(payload.get("sub"))
    result = await db.execute(select(Wallet).where(Wallet.buyer_id == user_id))
    wallet = result.scalar_one_or_none()

    if not wallet:
        wallet = Wallet(buyer_id=user_id)
        db.add(wallet)
        await db.flush()

    wallet.balance += request.amount
    txn = WalletTransaction(
        wallet_id=wallet.id,
        amount=request.amount,
        transaction_type="TopUp",
        description=f"Top-up saldo Rp {request.amount:,.0f}"
    )
    db.add(txn)
    await db.commit()
    await db.refresh(wallet)
    await db.refresh(txn)

    # Return updated wallet
    result2 = await db.execute(
        select(Wallet).options(selectinload(Wallet.transactions)).where(Wallet.id == wallet.id)
    )
    wallet = result2.scalar_one()
    txns = sorted(wallet.transactions, key=lambda t: t.created_at, reverse=True)[:20]
    return WalletResponse(
        id=wallet.id,
        balance=wallet.balance,
        transactions=[
            WalletTransactionResponse(
                id=t.id, amount=t.amount, transaction_type=t.transaction_type,
                description=t.description, created_at=t.created_at
            ) for t in txns
        ]
    )

@router.delete("/buyer/addresses/{address_id}")
async def delete_buyer_address(
    address_id: int,
    payload: dict = Depends(RequireActiveRole(["BUYER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id = uuid.UUID(payload.get("sub"))
    result = await db.execute(
        select(BuyerAddress).where(BuyerAddress.id == address_id, BuyerAddress.buyer_id == user_id)
    )
    address = result.scalar_one_or_none()
    if not address:
        raise HTTPException(status_code=404, detail="Alamat tidak ditemukan.")

    await db.delete(address)
    await db.commit()
    return {"message": "Alamat berhasil dihapus."}


# ==========================================
# PROMO ENDPOINTS (SELLER)
# ==========================================

@router.post("/seller/promos", response_model=PromoResponse)
async def create_promo(
    request: PromoCreateRequest,
    payload: dict = Depends(RequireActiveRole(["SELLER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    
    # Verify seller store
    store_res = await db.execute(select(Store).where(Store.seller_id == uuid.UUID(user_id_str)))
    store = store_res.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=400, detail="Anda belum memiliki toko.")
        
    # Verify products belong to store
    prod_res = await db.execute(
        select(Product).where(Product.id.in_(request.product_ids), Product.store_id == store.id)
    )
    products = prod_res.scalars().all()
    if len(products) != len(request.product_ids):
        raise HTTPException(status_code=400, detail="Beberapa produk tidak ditemukan atau bukan milik toko Anda.")
        
    new_promo = Promo(
        store_id=store.id,
        name=request.name,
        discount_percentage=request.discount_percentage,
        valid_from=request.valid_from,
        valid_until=request.valid_until,
        is_active=True
    )
    db.add(new_promo)
    await db.flush()
    
    for pid in request.product_ids:
        db.add(PromoProduct(promo_id=new_promo.id, product_id=pid))
        
    await db.commit()
    await db.refresh(new_promo)
    
    resp = PromoResponse.model_validate(new_promo)
    resp.product_ids = request.product_ids
    return resp

@router.get("/seller/promos", response_model=list[PromoResponse])
async def get_promos(
    payload: dict = Depends(RequireActiveRole(["SELLER"])),
    db: AsyncSession = Depends(get_db)
):
    user_id_str = payload.get("sub")
    store_res = await db.execute(select(Store).where(Store.seller_id == uuid.UUID(user_id_str)))
    store = store_res.scalar_one_or_none()
    if not store:
        return []
        
    result = await db.execute(
        select(Promo)
        .options(selectinload(Promo.promo_products))
        .where(Promo.store_id == store.id)
        .order_by(Promo.created_at.desc())
    )
    promos = result.scalars().all()
    
    responses = []
    for p in promos:
        resp = PromoResponse.model_validate(p)
        resp.product_ids = [pp.product_id for pp in p.promo_products]
        responses.append(resp)
    return responses

# ==========================================
# VOUCHER ENDPOINTS (ADMIN)
# ==========================================

@router.post("/admin/vouchers", response_model=VoucherResponse)
async def create_voucher(
    request: VoucherCreateRequest,
    payload: dict = Depends(RequireActiveRole(["ADMIN"])),
    db: AsyncSession = Depends(get_db)
):
    # Check if code exists
    existing = await db.execute(select(Voucher).where(Voucher.code == request.code.strip().upper()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Kode voucher sudah ada.")
        
    new_voucher = Voucher(
        code=request.code.strip().upper(),
        discount_type=request.discount_type,
        amount=request.amount,
        min_purchase=request.min_purchase,
        max_discount=request.max_discount,
        remaining_usage=request.remaining_usage,
        valid_from=request.valid_from,
        valid_until=request.valid_until
    )
    db.add(new_voucher)
    await db.commit()
    await db.refresh(new_voucher)
    return new_voucher

@router.get("/admin/vouchers", response_model=list[VoucherResponse])
async def get_vouchers(
    payload: dict = Depends(RequireActiveRole(["ADMIN"])),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Voucher).where(Voucher.is_deleted == False).order_by(Voucher.created_at.desc())
    )
    return result.scalars().all()
