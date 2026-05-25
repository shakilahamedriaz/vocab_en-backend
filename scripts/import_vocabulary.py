"""
Script to import vocabulary from the extracted JSON into the database.
Run: python -m scripts.import_vocabulary
"""
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.models.vocabulary import Vocabulary

# Create tables
Base.metadata.create_all(bind=engine)


def import_vocabulary():
    db = SessionLocal()

    # Read extracted vocabulary
    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "vocabulary.json")

    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found. Run extract_pdf.py first.")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        words = json.load(f)

    print(f"Importing {len(words)} words...")

    imported = 0
    skipped = 0

    for entry in words:
        word = entry.get("word", "").strip()
        pos = entry.get("pos", "").strip()
        synonyms = entry.get("synonyms", [])
        meaning_bengali = entry.get("meaning_bengali", "")

        if not word or not pos:
            skipped += 1
            continue

        # Check if already exists
        existing = db.query(Vocabulary).filter(
            Vocabulary.normalized_word == word.lower(),
            Vocabulary.part_of_speech == pos
        ).first()

        if existing:
            skipped += 1
            continue

        # Determine difficulty based on word length and characteristics
        difficulty = "intermediate"
        if len(word) <= 5:
            difficulty = "beginner"
        elif len(word) >= 10:
            difficulty = "advanced"

        # Determine IELTS band
        ielts_band = 6.0
        if len(word) >= 10:
            ielts_band = 7.0
        if len(word) >= 13:
            ielts_band = 8.0

        vocab_entry = Vocabulary(
            word=word,
            normalized_word=word.lower(),
            part_of_speech=pos,
            meaning=synonyms[0] if synonyms else word,  # Use first synonym as English meaning
            meaning_bengali=meaning_bengali,
            synonyms=synonyms,
            difficulty=difficulty,
            ielts_band=ielts_band,
            category="ielts",
            tags=["ielts", "vocabulary"],
            source="pdf_import"
        )

        db.add(vocab_entry)
        imported += 1

    db.commit()
    db.close()

    print(f"Import complete: {imported} imported, {skipped} skipped")


if __name__ == "__main__":
    import_vocabulary()
