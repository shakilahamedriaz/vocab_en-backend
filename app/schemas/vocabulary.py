from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class WordResponse(BaseModel):
    id: str
    word: str
    part_of_speech: str
    meaning: str
    meaning_bengali: Optional[str] = None
    pronunciation: Optional[str] = None
    difficulty: str
    ielts_band: Optional[float] = None
    synonyms: List[str] = []
    antonyms: List[str] = []
    collocations: List[str] = []
    examples: List[str] = []
    tags: List[str] = []
    category: Optional[str] = None

    class Config:
        from_attributes = True


class WordListResponse(BaseModel):
    words: List[WordResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class WordDetailResponse(WordResponse):
    word_family: List[dict] = []
    user_progress: Optional[dict] = None


class AIExplanation(BaseModel):
    simple_meaning: str
    academic_usage: str
    common_mistakes: List[str]
    synonym_differences: dict
    real_life_examples: List[str]
    tips: List[str] = []


class AISentence(BaseModel):
    sentence: str
    context: str
    band_level: float
    collocations: List[str] = []


class AISentenceResponse(BaseModel):
    word: str
    sentences: List[AISentence]


class QuizQuestion(BaseModel):
    id: str
    type: str
    question: str
    options: List[str]
    correct_answer: str
    explanation: str


class QuizResponse(BaseModel):
    quiz_id: str
    questions: List[QuizQuestion]
    total_questions: int
