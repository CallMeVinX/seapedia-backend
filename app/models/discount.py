from sqlalchemy import Column, BigInteger, String, Numeric, Integer, Boolean, DateTime, text
from sqlalchemy.orm import relationship
from app.db.session import Base

class Discount(Base):
    __tablename__ = "discounts"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    code = Column(String(50), unique=True, nullable=False)
    discount_type = Column(String(20), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    expiry_date = Column(DateTime(timezone=True), nullable=False)
    remaining_usage = Column(Integer, nullable=True)
    is_deleted = Column(Boolean, nullable=False, server_default=text("FALSE"))

    # Relationships
    orders = relationship("Order", back_populates="discount")
