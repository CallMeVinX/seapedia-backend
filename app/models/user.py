from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
from datetime import datetime, timezone
from app.db.session import Base

class AppRole(str, enum.Enum):
    Admin = "Admin"
    Seller = "Seller"
    Buyer = "Buyer"
    Driver = "Driver"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value.upper() == value.upper() or member.name.upper() == value.upper():
                    return member
        return None

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    avatar_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    # Relationships
    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    reviews = relationship("ApplicationReview", back_populates="user")
    store = relationship("Store", back_populates="seller", uselist=False)
    wallet = relationship("Wallet", back_populates="buyer", uselist=False)
    addresses = relationship("BuyerAddress", back_populates="buyer", cascade="all, delete-orphan")
    cart = relationship("Cart", back_populates="buyer", uselist=False)
    orders = relationship("Order", back_populates="buyer", foreign_keys="Order.buyer_id")
    delivery_jobs = relationship("DeliveryJob", back_populates="driver")

class UserRole(Base):
    __tablename__ = "user_roles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = Column(Enum(AppRole, name="app_role"), primary_key=True)
    assigned_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    # Relationships
    user = relationship("User", back_populates="roles")
