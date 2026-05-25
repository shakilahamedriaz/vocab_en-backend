from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.vocabulary import Vocabulary
from app.models.progress import UserProgress, ReviewHistory
from app.schemas.srs import DueWordResponse, DueWordsResponse, ReviewSubmit, ReviewResult, SRSStats
from app.services.srs_engine import SRSEngine

router = APIRouter(prefix="/srs", tags=["SRS"])


@router.get("/due-words", response_model=DueWordsResponse)
async def get_due_words(
    limit: int = Query(20, ge=1, le=50),
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    now = datetime.utcnow()

    # Get words due for review
    query = db.query(UserProgress, Vocabulary).join(
        Vocabulary, UserProgress.word_id == Vocabulary.id
    ).filter(
        UserProgress.user_id == current_user.id,
        UserProgress.next_review <= now
    ).order_by(UserProgress.next_review)

    if category:
        query = query.filter(Vocabulary.category == category)

    results = query.limit(limit).all()

    # If not enough due words, add new words
    if len(results) < limit:
        learned_word_ids = db.query(UserProgress.word_id).filter(
            UserProgress.user_id == current_user.id
        ).subquery()

        new_words = db.query(Vocabulary).filter(
            ~Vocabulary.id.in_(learned_word_ids)
        ).limit(limit - len(results)).all()

        for word in new_words:
            results.append((None, word))

    due_words = []
    for progress, word in results:
        overdue_days = 0
        if progress and progress.next_review:
            overdue_days = max(0, (now - progress.next_review).days)

        due_words.append(DueWordResponse(
            word_id=word.id,
            word=word.word,
            part_of_speech=word.part_of_speech,
            meaning=word.meaning,
            meaning_bengali=word.meaning_bengali,
            pronunciation=word.pronunciation,
            synonyms=word.synonyms or [],
            last_reviewed=progress.last_reviewed_at if progress else None,
            current_interval=progress.interval if progress else 0,
            repetitions=progress.repetitions if progress else 0,
            easiness_factor=progress.easiness_factor if progress else 2.5,
            overdue_days=overdue_days,
            mastery_status=progress.status if progress else "new"
        ))

    total_due = db.query(UserProgress).filter(
        UserProgress.user_id == current_user.id,
        UserProgress.next_review <= now
    ).count()

    return DueWordsResponse(
        due_words=due_words,
        total_due=total_due,
        review_batch_size=limit
    )


@router.post("/review", response_model=ReviewResult)
async def submit_review(
    review: ReviewSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if review.quality < 0 or review.quality > 5:
        raise HTTPException(status_code=400, detail="Quality must be between 0 and 5")

    # Get or create progress
    progress = db.query(UserProgress).filter(
        UserProgress.user_id == current_user.id,
        UserProgress.word_id == review.word_id
    ).first()

    if not progress:
        progress = UserProgress(
            user_id=current_user.id,
            word_id=review.word_id,
            status="new",
            interval=0,
            repetitions=0,
            easiness_factor=2.5,
            first_seen_at=datetime.utcnow()
        )
        db.add(progress)

    # Store previous state
    previous_status = progress.status or "new"
    previous_interval = progress.interval or 0

    # Calculate next review
    new_interval, new_reps, new_ef, next_review = SRSEngine.calculate_next_review(
        quality=review.quality,
        repetitions=progress.repetitions,
        easiness_factor=progress.easiness_factor,
        current_interval=progress.interval
    )

    # Update progress
    progress.interval = new_interval
    progress.repetitions = new_reps
    progress.easiness_factor = new_ef
    progress.next_review = next_review
    progress.last_reviewed_at = datetime.utcnow()
    progress.total_reviews = (progress.total_reviews or 0) + 1
    if review.quality >= 3:
        progress.correct_reviews = (progress.correct_reviews or 0) + 1
    else:
        progress.correct_reviews = progress.correct_reviews or 0
    progress.accuracy = (progress.correct_reviews / progress.total_reviews) * 100 if progress.total_reviews > 0 else 0
    progress.status = SRSEngine.classify_mastery(new_reps, new_ef, progress.accuracy)

    # Save review history
    history = ReviewHistory(
        user_id=current_user.id,
        word_id=review.word_id,
        quality=review.quality,
        response_time_ms=review.response_time_ms,
        review_mode=review.review_mode
    )
    db.add(history)

    # Update user streak
    today = datetime.utcnow().date().isoformat()
    if current_user.last_active_date != today:
        yesterday = (datetime.utcnow().date() - timedelta(days=1)).isoformat()
        if current_user.last_active_date == yesterday:
            current_user.streak = (current_user.streak or 0) + 1
        else:
            current_user.streak = 1
        current_user.longest_streak = max(current_user.longest_streak or 0, current_user.streak or 1)
        current_user.last_active_date = today

    db.commit()

    return ReviewResult(
        word_id=review.word_id,
        previous_status=previous_status,
        new_status=progress.status,
        previous_interval=previous_interval,
        new_interval=new_interval,
        next_review=next_review,
        easiness_factor=new_ef,
        repetitions=new_reps
    )


@router.get("/stats", response_model=SRSStats)
async def get_srs_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Progress counts by status
    status_counts = db.query(
        UserProgress.status,
        func.count(UserProgress.id)
    ).filter(
        UserProgress.user_id == current_user.id
    ).group_by(UserProgress.status).all()

    stats = {s: c for s, c in status_counts}

    # Due today
    due_today = db.query(func.count(UserProgress.id)).filter(
        UserProgress.user_id == current_user.id,
        UserProgress.next_review <= now
    ).scalar()

    # Completed today
    completed_today = db.query(func.count(ReviewHistory.id)).filter(
        ReviewHistory.user_id == current_user.id,
        ReviewHistory.reviewed_at >= today_start
    ).scalar()

    # Today's accuracy
    today_reviews = db.query(ReviewHistory).filter(
        ReviewHistory.user_id == current_user.id,
        ReviewHistory.reviewed_at >= today_start
    ).all()

    accuracy_today = 0
    if today_reviews:
        correct = sum(1 for r in today_reviews if r.quality >= 3)
        accuracy_today = (correct / len(today_reviews)) * 100

    return SRSStats(
        total_words=sum(stats.values()),
        new=stats.get("new", 0),
        learning=stats.get("learning", 0),
        familiar=stats.get("familiar", 0),
        mastered=stats.get("mastered", 0),
        due_today=due_today,
        completed_today=completed_today,
        accuracy_today=round(accuracy_today, 1),
        streak=current_user.streak
    )


@router.get("/history")
async def get_review_history(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    since = datetime.utcnow() - timedelta(days=days)

    history = db.query(
        func.date(ReviewHistory.reviewed_at).label("date"),
        func.count(ReviewHistory.id).label("count"),
        func.avg(ReviewHistory.quality).label("avg_quality")
    ).filter(
        ReviewHistory.user_id == current_user.id,
        ReviewHistory.reviewed_at >= since
    ).group_by(
        func.date(ReviewHistory.reviewed_at)
    ).all()

    return {
        "history": [
            {
                "date": str(h.date),
                "reviews": h.count,
                "avg_quality": round(float(h.avg_quality), 2)
            }
            for h in history
        ]
    }
