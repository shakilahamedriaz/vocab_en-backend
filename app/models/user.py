import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    
    # Learning
    daily_goal = Column(Integer, default=20)
    streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    last_active_date = Column(String, nullable=True)
    
    # Subscription
    subscription_tier = Column(String(20), default="free")
    
    # Preferences
    theme = Column(String(10), default="system")
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
