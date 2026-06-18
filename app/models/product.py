from sqlalchemy import Column, BigInteger, String, Text, Numeric, Integer, Boolean, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.session import Base

class Store(Base):
    __tablename__ = "stores"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), unique=True)
    store_name = Column(String(100), unique=True, nullable=False)
    logo_url = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    # Relationships
    seller = relationship("User", back_populates="store")
    products = relationship("Product", back_populates="store", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="store")

class Product(Base):
    __tablename__ = "products"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    store_id = Column(BigInteger, ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    price = Column(Numeric(12, 2), nullable=False) # Check constraint >= 0 in DB
    stock = Column(Integer, nullable=False) # Check constraint >= 0 in DB
    is_deleted = Column(Boolean, nullable=False, server_default=text("FALSE"))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    # Relationships
    store = relationship("Store", back_populates="products")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    cart_items = relationship("CartItem", back_populates="product", cascade="all, delete-orphan")
    order_items = relationship("OrderItem", back_populates="product")

class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    product_id = Column(BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(Text, nullable=False)
    is_primary = Column(Boolean, nullable=False, server_default=text("FALSE"))
    display_order = Column(Integer, nullable=False, server_default=text("0"))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    # Relationships
    product = relationship("Product", back_populates="images")
