from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.session import get_db
from app.api.dependencies import get_token_payload
from app.services.auth_service import get_user_roles
from app.models.user import User
from app.models.product import Product
from app.models.review import ApplicationReview

from app.schemas.auth_schema import UserProfileResponse
from app.schemas.product_schema import ProductResponse
from app.schemas.review_schema import ReviewCreateRequest, ReviewResponse

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
        .options(selectinload(Product.images))
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
            "image_url": image_url
        })
        
    return response_list

@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images))
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
        "image_url": image_url
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
