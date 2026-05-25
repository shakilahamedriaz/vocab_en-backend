from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional, List
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.vocabulary import Vocabulary
from app.models.progress import UserProgress
from app.schemas.vocabulary import WordResponse, WordListResponse, WordDetailResponse
from app.services.ai_service import ai_service
import json

router = APIRouter(prefix="/vocabulary", tags=["Vocabulary"])


@router.get("/words", response_model=WordListResponse)
async def list_words(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    difficulty: Optional[str] = None,
    pos: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Vocabulary)

    # Search
    if search:
        search_term = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(Vocabulary.normalized_word).like(search_term),
                func.lower(Vocabulary.meaning).like(search_term)
            )
        )

    # Filters
    if difficulty:
        query = query.filter(Vocabulary.difficulty == difficulty)
    if pos:
        query = query.filter(Vocabulary.part_of_speech == pos)
    if category:
        query = query.filter(Vocabulary.category == category)

    # Count
    total = query.count()
    total_pages = (total + limit - 1) // limit

    # Paginate
    words = query.offset((page - 1) * limit).limit(limit).all()

    return WordListResponse(
        words=[WordResponse.model_validate(w) for w in words],
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages
    )


@router.get("/words/{word_id}", response_model=WordDetailResponse)
async def get_word(
    word_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    word = db.query(Vocabulary).filter(Vocabulary.id == word_id).first()
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")

    # Get user progress
    progress = db.query(UserProgress).filter(
        UserProgress.user_id == current_user.id,
        UserProgress.word_id == word_id
    ).first()

    progress_data = None
    if progress:
        progress_data = {
            "status": progress.status,
            "interval": progress.interval,
            "repetitions": progress.repetitions,
            "easiness_factor": progress.easiness_factor,
            "next_review": progress.next_review.isoformat() if progress.next_review else None,
            "accuracy": progress.accuracy
        }

    result = WordDetailResponse.model_validate(word)
    result.user_progress = progress_data
    return result


@router.get("/words/{word_id}/explain")
async def explain_word(
    word_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    word = db.query(Vocabulary).filter(Vocabulary.id == word_id).first()
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")

    if word.ai_explanation:
        return {"word": word.word, "explanation": word.ai_explanation, "cached": True}

    explanation = await ai_service.generate_explanation(
        word.word, word.part_of_speech, word.synonyms or [], word.meaning
    )
    word.ai_explanation = explanation
    db.commit()
    return {"word": word.word, "explanation": explanation, "cached": False}


@router.get("/words/{word_id}/sentences")
async def generate_sentences(
    word_id: str,
    count: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    word = db.query(Vocabulary).filter(Vocabulary.id == word_id).first()
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")

    sentences = await ai_service.generate_sentences(
        word.word, word.part_of_speech, word.meaning, count
    )
    return {"word": word.word, "sentences": sentences}


def _is_corrupted_bengali(text: str) -> bool:
    """Detect PDF-extraction corruption in Bengali text."""
    if not text:
        return True
    corruption_markers = ["ক্ল", "জে", "জো", "যো", "ক্লি", "পদও"]
    return any(m in text for m in corruption_markers)


@router.post("/words/{word_id}/fix-bengali")
async def fix_bengali_meaning(
    word_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Regenerate Bengali meaning for a single word via AI."""
    word = db.query(Vocabulary).filter(Vocabulary.id == word_id).first()
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")

    new_meaning = await ai_service.generate_bengali_meaning(
        word.word, word.part_of_speech, word.meaning
    )
    if not new_meaning:
        raise HTTPException(status_code=503, detail="AI service unavailable — check API quota")

    word.meaning_bengali = new_meaning
    db.commit()
    return {"word": word.word, "meaning_bengali": new_meaning}


@router.get("/stats")
async def get_vocab_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    total = db.query(Vocabulary).count()
    
    # Get user's progress stats
    from sqlalchemy import func
    progress_stats = db.query(
        UserProgress.status,
        func.count(UserProgress.id)
    ).filter(
        UserProgress.user_id == current_user.id
    ).group_by(UserProgress.status).all()

    stats = {status: count for status, count in progress_stats}

    return {
        "total_words": total,
        "new": stats.get("new", 0),
        "learning": stats.get("learning", 0),
        "familiar": stats.get("familiar", 0),
        "mastered": stats.get("mastered", 0)
    }
