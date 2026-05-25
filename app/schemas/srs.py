from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class DueWordResponse(BaseModel):
    word_id: str
    word: str
    part_of_speech: str
    meaning: str
    meaning_bengali: Optional[str] = None
    pronunciation: Optional[str] = None
    synonyms: List[str] = []
    last_reviewed: Optional[datetime] = None
    current_interval: int = 0
    repetitions: int = 0
    easiness_factor: float = 2.5
    overdue_days: int = 0
    mastery_status: str = "new"


class DueWordsResponse(BaseModel):
    due_words: List[DueWordResponse]
    total_due: int
    review_batch_size: int


class ReviewSubmit(BaseModel):
    word_id: str
    quality: int  # 0-5
    response_time_ms: Optional[int] = None
    review_mode: str = "srs"


class ReviewResult(BaseModel):
    word_id: str
    previous_status: str
    new_status: str
    previous_interval: int
    new_interval: int
    next_review: datetime
    easiness_factor: float
    repetitions: int


class SRSStats(BaseModel):
    total_words: int
    new: int
    learning: int
    familiar: int
    mastered: int
    due_today: int
    completed_today: int
    accuracy_today: float
    streak: int
