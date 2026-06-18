from sqlalchemy import Column, BigInteger, String, Text, Numeric, Integer, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.session import Base

class BuyerAddress(Base):
    __tablename__ = "buyer_addresses"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    full_address = Column(Text, nullable=False)

    # Relationships
    buyer = relationship("User", back_populates="addresses")
    orders = relationship("Order", back_populates="address")

class Order(Base):
    __tablename__ = "orders"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    store_id = Column(BigInteger, ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    address_id = Column(BigInteger, ForeignKey("buyer_addresses.id", ondelete="RESTRICT"), nullable=False)
    discount_id = Column(BigInteger, ForeignKey("discounts.id", ondelete="SET NULL"), nullable=True)
    delivery_method = Column(String(20), nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False)
    discount_amount = Column(Numeric(12, 2), nullable=False, server_default=text("0.00"))
    delivery_fee = Column(Numeric(12, 2), nullable=False)
    ppn_amount = Column(Numeric(12, 2), nullable=False)
    final_total = Column(Numeric(12, 2), nullable=False)
    current_status = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    # Relationships
    buyer = relationship("User", back_populates="orders", foreign_keys=[buyer_id])
    store = relationship("Store", back_populates="orders")
    address = relationship("BuyerAddress", back_populates="orders")
    discount = relationship("Discount", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    status_history = relationship("OrderStatusHistory", back_populates="order", cascade="all, delete-orphan")
    delivery_job = relationship("DeliveryJob", back_populates="order", uselist=False)

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    order_id = Column(BigInteger, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    product_id = Column(BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price_at_purchase = Column(Numeric(12, 2), nullable=False)

    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")

class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    order_id = Column(BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    status_name = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    # Relationships
    order = relationship("Order", back_populates="status_history")

class DeliveryJob(Base):
    __tablename__ = "delivery_jobs"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    order_id = Column(BigInteger, ForeignKey("orders.id", ondelete="RESTRICT"), unique=True, nullable=False)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    driver_earning = Column(Numeric(12, 2), nullable=False)
    status = Column(String(50), nullable=False)
    taken_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    order = relationship("Order", back_populates="delivery_job")
    driver = relationship("User", back_populates="delivery_jobs")
