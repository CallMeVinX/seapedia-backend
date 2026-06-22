from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.session import get_db
from app.api.dependencies import get_token_payload, RequireActiveRole
from app.services.auth_service import get_user_roles
from app.models.user import User
from app.models.product import Product, Store
from app.models.review import ApplicationReview
from app.models.cart import Cart, CartItem
from app.models.order import Order, OrderItem
from app.models.discount import Discount

from app.schemas.auth_schema import UserProfileResponse
from app.schemas.product_schema import ProductResponse
from app.schemas.review_schema import ReviewCreateRequest, ReviewResponse
from app.schemas.order_schema import CheckoutRequest, CheckoutResponse
from app.schemas.cart_schema import CartItemRequest, CartItemResponse, CartResponse
from app.schemas.address_schema import AddressRequest, AddressResponse
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
        
        items_response.append(CartItemResponse(
            id=item.id,
            product_id=item.product.id,
            product_name=item.product.name,
            product_image=image_url,
            store_id=item.product.store_id,
            store_name=store_name,
            quantity=item.quantity,
            unit_price=int(item.product.price),
            total_price=int(item.product.price * item.quantity)
        ))
        total_items += item.quantity
        total_price += item.product.price * item.quantity
        
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
        
    # 2. Validate Single-Store
    store_ids = {item.product.store_id for item in selected_items}
    if len(store_ids) > 1:
        raise HTTPException(status_code=400, detail="Checkout Gagal: Anda hanya dapat melakukan checkout barang dari 1 toko dalam satu waktu.")
        
    store_id = list(store_ids)[0]
    
    # 3. Lock Products for Race Condition (SELECT ... FOR UPDATE)
    product_ids = [item.product_id for item in selected_items]
    prod_result = await db.execute(
        select(Product)
        .where(Product.id.in_(product_ids))
        .with_for_update()
    )
    products_locked = {p.id: p for p in prod_result.scalars().all()}
    
    subtotal = Decimal('0.00')
    
    for item in selected_items:
        locked_product = products_locked.get(item.product_id)
        if not locked_product:
            raise HTTPException(status_code=400, detail=f"Produk {item.product_id} tidak ditemukan.")
        if locked_product.stock < item.quantity:
            raise HTTPException(status_code=400, detail=f"Stok tidak cukup untuk {locked_product.name}. Tersisa {locked_product.stock} unit.")
        
        # Deduct stock
        locked_product.stock -= item.quantity
        
        # Calculate subtotal
        subtotal += locked_product.price * item.quantity
        
    # 4. Calculate Discount
    discount_amount = Decimal('0.00')
    discount_id = None
    if request.discount_code:
        disc_result = await db.execute(
            select(Discount).where(Discount.code == request.discount_code, Discount.is_deleted == False)
        )
        discount = disc_result.scalar_one_or_none()
        if not discount:
            raise HTTPException(status_code=400, detail="Kode diskon tidak valid.")
        discount_amount = discount.amount
        discount_id = discount.id
        
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
    ppn_amount = ((subtotal - discount_amount) * Decimal('0.12')).quantize(Decimal('0.01'))
    if ppn_amount < 0:
        ppn_amount = Decimal('0.00')
        
    final_total = subtotal - discount_amount + delivery_fee + ppn_amount
    if final_total < 0:
        final_total = Decimal('0.00')
        
    # 7. Create Order
    new_order = Order(
        buyer_id=user_id,
        store_id=store_id,
        address_id=request.address_id,
        discount_id=discount_id,
        delivery_method=db_delivery_method,
        subtotal=subtotal,
        discount_amount=discount_amount,
        delivery_fee=delivery_fee,
        ppn_amount=ppn_amount,
        final_total=final_total,
        current_status="Sedang Dikemas"
    )
    db.add(new_order)
    await db.flush() # To get new_order.id
    
    # 8. Create Order Items
    for item in selected_items:
        locked_product = products_locked[item.product_id]
        order_item = OrderItem(
            order_id=new_order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price_at_purchase=locked_product.price
        )
        db.add(order_item)
        
    # 9. Clear Selected Cart Items
    for item in selected_items:
        await db.delete(item)
        
    await db.commit()
        
    return CheckoutResponse(
        order_id=new_order.id,
        subtotal=subtotal,
        discount_amount=discount_amount,
        delivery_fee=delivery_fee,
        ppn_amount=ppn_amount,
        final_total=final_total,
        message="Checkout berhasil!"
    )
