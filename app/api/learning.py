from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import random
import uuid
from datetime import datetime
from pydantic import BaseModel
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.vocabulary import Vocabulary
from app.models.progress import UserProgress
from app.services.ai_service import ai_service

router = APIRouter(prefix="/learning", tags=["Learning"])


class QuizResultItem(BaseModel):
    word_id: str
    is_correct: bool


class QuizSubmit(BaseModel):
    results: List[QuizResultItem]


@router.get("/flashcards")
async def get_flashcard_deck(
    limit: int = Query(20, ge=1, le=50),
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    mode: str = Query("mixed"),  # new, review, mixed
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    now = datetime.utcnow()

    if mode == "review":
        query = db.query(Vocabulary).join(
            UserProgress, UserProgress.word_id == Vocabulary.id
        ).filter(
            UserProgress.user_id == current_user.id,
            UserProgress.next_review <= now
        )
        if category:
            query = query.filter(Vocabulary.category == category)
        if difficulty:
            query = query.filter(Vocabulary.difficulty == difficulty)
        words = query.limit(limit).all()

    elif mode == "new":
        learned_ids = db.query(UserProgress.word_id).filter(
            UserProgress.user_id == current_user.id
        ).subquery()
        query = db.query(Vocabulary).filter(~Vocabulary.id.in_(learned_ids))
        if category:
            query = query.filter(Vocabulary.category == category)
        if difficulty:
            query = query.filter(Vocabulary.difficulty == difficulty)
        words = query.limit(limit).all()

    else:
        # Mixed: due words first, fill the rest with new words
        due_query = db.query(Vocabulary).join(
            UserProgress, UserProgress.word_id == Vocabulary.id
        ).filter(
            UserProgress.user_id == current_user.id,
            UserProgress.next_review <= now
        )
        if category:
            due_query = due_query.filter(Vocabulary.category == category)
        if difficulty:
            due_query = due_query.filter(Vocabulary.difficulty == difficulty)
        due_words = due_query.limit(limit // 2).all()

        remaining = limit - len(due_words)
        learned_ids = db.query(UserProgress.word_id).filter(
            UserProgress.user_id == current_user.id
        ).subquery()
        new_query = db.query(Vocabulary).filter(~Vocabulary.id.in_(learned_ids))
        if category:
            new_query = new_query.filter(Vocabulary.category == category)
        if difficulty:
            new_query = new_query.filter(Vocabulary.difficulty == difficulty)
        new_words = new_query.limit(remaining).all()

        words = due_words + new_words

    random.shuffle(words)

    return {
        "deck_size": len(words),
        "words": [
            {
                "id": w.id,
                "word": w.word,
                "part_of_speech": w.part_of_speech,
                "meaning": w.meaning,
                "meaning_bengali": w.meaning_bengali,
                "pronunciation": w.pronunciation,
                "synonyms": w.synonyms or [],
                "examples": w.examples or [],
                "difficulty": w.difficulty
            }
            for w in words
        ]
    }


@router.get("/quiz")
async def generate_quiz(
    count: int = Query(10, ge=5, le=30),
    category: Optional[str] = None,
    quiz_type: str = Query("meaning"),  # meaning, synonym, mixed
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Vocabulary)
    if category:
        query = query.filter(Vocabulary.category == category)

    all_words = query.all()
    if len(all_words) < 4:
        raise HTTPException(status_code=400, detail="Not enough words for quiz")

    quiz_words = random.sample(all_words, min(count, len(all_words)))

    questions = []
    for word in quiz_words:
        other_words = [w for w in all_words if w.id != word.id]
        wrong_options = random.sample(other_words, min(3, len(other_words)))

        if quiz_type == "synonym" and word.synonyms:
            correct = random.choice(word.synonyms)
            wrong_synonyms = []
            for w in wrong_options:
                if w.synonyms:
                    candidate = random.choice(w.synonyms)
                    if candidate != correct and candidate not in wrong_synonyms:
                        wrong_synonyms.append(candidate)

            if len(wrong_synonyms) < 3:
                # Fall back to meanings if not enough unique synonyms
                fallback = [w.meaning for w in wrong_options if w.meaning != correct]
                wrong_synonyms = (wrong_synonyms + fallback)[:3]

            options = [correct] + wrong_synonyms[:3]
            random.shuffle(options)

            questions.append({
                "id": str(uuid.uuid4()),
                "word_id": word.id,
                "type": "synonym",
                "question": f"Which word is a synonym of '{word.word}'?",
                "options": options,
                "correct_answer": correct,
                "explanation": f"'{correct}' is a synonym of '{word.word}'."
            })
        else:
            correct = word.meaning
            wrong_meanings = []
            for w in wrong_options:
                if w.meaning != correct and w.meaning not in wrong_meanings:
                    wrong_meanings.append(w.meaning)

            options = [correct] + wrong_meanings[:3]
            random.shuffle(options)

            questions.append({
                "id": str(uuid.uuid4()),
                "word_id": word.id,
                "type": "meaning",
                "question": f"What does '{word.word}' mean?",
                "options": options,
                "correct_answer": correct,
                "explanation": f"'{word.word}' means: {word.meaning}"
            })

    return {
        "quiz_id": str(uuid.uuid4()),
        "questions": questions,
        "total_questions": len(questions)
    }


@router.post("/quiz/submit")
async def submit_quiz_results(
    payload: QuizSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.services.srs_engine import SRSEngine

    correct_count = 0
    total = len(payload.results)

    for result in payload.results:
        if result.is_correct:
            correct_count += 1

        progress = db.query(UserProgress).filter(
            UserProgress.user_id == current_user.id,
            UserProgress.word_id == result.word_id
        ).first()

        if not progress:
            progress = UserProgress(
                user_id=current_user.id,
                word_id=result.word_id,
                total_reviews=0,
                correct_reviews=0
            )
            db.add(progress)
            db.flush()  # populate defaults before arithmetic

        quality = 4 if result.is_correct else 1
        new_interval, new_reps, new_ef, next_review = SRSEngine.calculate_next_review(
            quality=quality,
            repetitions=progress.repetitions or 0,
            easiness_factor=progress.easiness_factor or 2.5,
            current_interval=progress.interval or 0
        )

        progress.interval = new_interval
        progress.repetitions = new_reps
        progress.easiness_factor = new_ef
        progress.next_review = next_review
        progress.total_reviews = (progress.total_reviews or 0) + 1
        if result.is_correct:
            progress.correct_reviews = (progress.correct_reviews or 0) + 1
        else:
            progress.correct_reviews = progress.correct_reviews or 0
        progress.accuracy = (progress.correct_reviews / progress.total_reviews) * 100

    db.commit()

    return {
        "total": total,
        "correct": correct_count,
        "accuracy": round((correct_count / total * 100) if total > 0 else 0, 1)
    }
