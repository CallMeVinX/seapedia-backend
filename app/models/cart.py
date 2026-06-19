from sqlalchemy import Column, BigInteger, Integer, ForeignKey, UniqueConstraint, text, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.session import Base

class Cart(Base):
    __tablename__ = "carts"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Relationships
    buyer = relationship("User", back_populates="cart")
    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")

class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    cart_id = Column(BigInteger, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint('cart_id', 'product_id', name='uq_cart_product'),
        CheckConstraint('quantity > 0', name='chk_cart_item_quantity'),
    )

    # Relationships
    cart = relationship("Cart", back_populates="items")
    product = relationship("Product", back_populates="cart_items")
