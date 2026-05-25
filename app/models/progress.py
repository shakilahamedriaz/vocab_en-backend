import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey
from app.core.database import Base


class UserProgress(Base):
    __tablename__ = "user_progress"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    word_id = Column(String, ForeignKey("vocabulary.id"), nullable=False, index=True)
    
    # SRS Parameters
    status = Column(String(20), default="new")  # new, learning, familiar, mastered
    interval = Column(Integer, default=0)
    repetitions = Column(Integer, default=0)
    easiness_factor = Column(Float, default=2.5)
    next_review = Column(DateTime, nullable=True, index=True)
    last_reviewed_at = Column(DateTime, nullable=True)
    
    # Performance
    total_reviews = Column(Integer, default=0)
    correct_reviews = Column(Integer, default=0)
    accuracy = Column(Float, default=0.0)
    
    # Metadata
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReviewHistory(Base):
    __tablename__ = "review_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    word_id = Column(String, ForeignKey("vocabulary.id"), nullable=False, index=True)
    
    quality = Column(Integer, nullable=False)  # 0-5
    response_time_ms = Column(Integer, nullable=True)
    review_mode = Column(String(30), nullable=True)
    
    reviewed_at = Column(DateTime, default=datetime.utcnow)
