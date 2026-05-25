import re
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.vocabulary import Vocabulary

router = APIRouter(prefix="/games", tags=["Games"])


def short_meaning(text: str, max_len: int = 72) -> str:
    """Return a concise, readable meaning for game cards."""
    if not text:
        return ""
    # Strip leading "1. " / "2. " numbering
    cleaned = re.sub(r"^\s*\d+\.\s*", "", text.strip())
    # Split on major clause separators, pick the longest clause ≤ max_len
    candidates = re.split(r";?\s+--\s+|;\s+", cleaned)
    chosen = ""
    for c in candidates:
        c = c.strip().rstrip(" .;,-")
        c = re.sub(r"^\s*(as|e\.g\.)[,\s].*$", "", c, flags=re.I).strip()
        if len(c) >= 8 and len(c) <= max_len and len(c) > len(chosen):
            chosen = c
    if not chosen:
        # Fallback: hard truncate
        chosen = cleaned[:max_len].rsplit(" ", 1)[0].rstrip(" .;,-") + "…"
    if len(chosen) > max_len:
        chosen = chosen[:max_len].rsplit(" ", 1)[0].rstrip(" .;,-") + "…"
    return chosen


@router.get("/random")
async def random_words(
    count: int = Query(10, ge=1, le=50),
    need_synonyms: bool = Query(False),
    min_length: int = Query(3, ge=2, le=20),
    max_length: int = Query(14, ge=3, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return random vocabulary words for the Word Arena games."""
    q = db.query(Vocabulary).filter(
        func.length(Vocabulary.word) >= min_length,
        func.length(Vocabulary.word) <= max_length,
    )
    rows = q.order_by(func.random()).limit(count * 4).all()

    out = []
    for w in rows:
        syns = w.synonyms or []
        if need_synonyms and len(syns) < 2:
            continue
        sm = short_meaning(w.meaning or "")
        if not sm:
            continue
        out.append({
            "id": w.id,
            "word": w.word,
            "part_of_speech": w.part_of_speech,
            "meaning": w.meaning,
            "short_meaning": sm,
            "meaning_bengali": w.meaning_bengali,
            "synonyms": syns,
            "antonyms": w.antonyms or [],
            "difficulty": w.difficulty,
        })
        if len(out) >= count:
            break

    return {"count": len(out), "words": out}


@router.get("/distractors")
async def get_distractors(
    exclude: str = Query(...),
    count: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return random words to use as wrong-answer distractors."""
    exclude_ids = [s.strip() for s in exclude.split(",") if s.strip()]
    q = db.query(Vocabulary).filter(~Vocabulary.id.in_(exclude_ids))
    rows = q.order_by(func.random()).limit(count).all()
    return {
        "words": [
            {"id": w.id, "word": w.word, "meaning": w.meaning}
            for w in rows
        ]
    }
