from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, text, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.session import Base

class ApplicationReview(Base):
    __tablename__ = "application_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewer_name = Column(String(150), nullable=False)
    rating = Column(Integer, nullable=False)
    comment_text = Column(Text, nullable=False)
    attachment_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        CheckConstraint('rating >= 1 AND rating <= 5', name='chk_rating_range'),
    )

    # Relationships
    user = relationship("User", back_populates="reviews")
