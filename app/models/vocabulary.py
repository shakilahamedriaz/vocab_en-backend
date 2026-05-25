import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON
from app.core.database import Base


class Vocabulary(Base):
    __tablename__ = "vocabulary"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    word = Column(String(100), nullable=False, index=True)
    normalized_word = Column(String(100), nullable=False, index=True)
    part_of_speech = Column(String(20), nullable=False)
    meaning = Column(Text, nullable=False)
    meaning_bengali = Column(Text, nullable=True)
    
    # Pronunciation
    pronunciation = Column(String(100), nullable=True)
    
    # Classification
    difficulty = Column(String(20), default="intermediate")
    ielts_band = Column(Float, nullable=True)
    
    # JSON fields
    synonyms = Column(JSON, default=[])
    antonyms = Column(JSON, default=[])
    collocations = Column(JSON, default=[])
    word_family = Column(JSON, default=[])
    examples = Column(JSON, default=[])
    
    # Tags
    tags = Column(JSON, default=[])
    category = Column(String(50), nullable=True)
    
    # Source
    source = Column(String(50), default="pdf_upload")

    # Cached AI explanation (generated lazily on first /explain request)
    ai_explanation = Column(JSON, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
