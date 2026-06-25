from sqlalchemy import Column, BigInteger, String, Numeric, Boolean, DateTime, ForeignKey, text, CheckConstraint
from sqlalchemy.orm import relationship
from app.db.session import Base


class Promo(Base):
    """
    Promo — Diskon otomatis yang melekat pada produk.
    Dikelola oleh Seller untuk strategi marketing toko mereka.
    Pembeli tidak perlu memasukkan kode; harga coret tampil otomatis.
    """
    __tablename__ = "promos"

    id = Column(BigInteger, primary_key=True, server_default=text("GENERATED ALWAYS AS IDENTITY"))
    store_id = Column(BigInteger, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    discount_percentage = Column(Numeric(5, 2), nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    __table_args__ = (
        CheckConstraint('discount_percentage > 0 AND discount_percentage <= 100', name='chk_promo_percentage'),
    )

    # Relationships
    store = relationship("Store", back_populates="promos")
    promo_products = relationship("PromoProduct", back_populates="promo", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="promo")


class PromoProduct(Base):
    """
    Pivot table — Many-to-Many antara Promo dan Product.
    Satu promo bisa berlaku untuk banyak produk sekaligus.
    """
    __tablename__ = "promo_products"

    promo_id = Column(BigInteger, ForeignKey("promos.id", ondelete="CASCADE"), primary_key=True)
    product_id = Column(BigInteger, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)

    # Relationships
    promo = relationship("Promo", back_populates="promo_products")
    product = relationship("Product", back_populates="promo_products")
