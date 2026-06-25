from sqlalchemy import Column, BigInteger, String, Numeric, Integer, Boolean, DateTime, text, CheckConstraint
from sqlalchemy.orm import relationship
from app.db.session import Base

class Voucher(Base):
    """
    Voucher — Diskon berbentuk kode kupon yang harus diklaim/diinput manual.
    Dikelola oleh Admin platform.
    Pembeli harus menginput kode ini saat checkout.
    """
    __tablename__ = "vouchers"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    code = Column(String(50), unique=True, nullable=False)
    discount_type = Column(String(20), nullable=False) # "PERCENTAGE" or "FIXED"
    amount = Column(Numeric(12, 2), nullable=False)
    min_purchase = Column(Numeric(12, 2), nullable=False, server_default=text("0.00"))
    max_discount = Column(Numeric(12, 2), nullable=True) # Max discount for percentage type
    remaining_usage = Column(Integer, nullable=True)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=False)
    is_deleted = Column(Boolean, nullable=False, server_default=text("FALSE"))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    __table_args__ = (
        CheckConstraint('amount > 0', name='chk_voucher_amount'),
        CheckConstraint('min_purchase >= 0', name='chk_voucher_min_purchase'),
        CheckConstraint('max_discount >= 0', name='chk_voucher_max_discount'),
        CheckConstraint('remaining_usage >= 0', name='chk_voucher_remaining_usage'),
    )

    # Relationships
    orders = relationship("Order", back_populates="voucher")
