"""
Fix vocabulary meanings using local dictionary file.
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.vocabulary import Vocabulary


def load_dictionary(path: str) -> dict:
    """Load JSON dictionary."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_definition(word: str, dictionary: dict) -> str | None:
    """Get definition from dictionary."""
    word_lower = word.lower()
    
    # Direct lookup
    if word_lower in dictionary:
        defn = dictionary[word_lower]
        if isinstance(defn, str) and len(defn) > 3:
            return defn[:200]  # Limit length
    
    return None


def fix_meanings():
    dict_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dictionary.json")
    
    print("Loading dictionary...")
    dictionary = load_dictionary(dict_path)
    print(f"Loaded {len(dictionary)} entries")
    
    db = SessionLocal()
    words = db.query(Vocabulary).all()
    total = len(words)
    fixed = 0
    
    print(f"Processing {total} words...")
    
    for i, word in enumerate(words):
        # Check if meaning needs fix
        needs_fix = False
        
        if word.synonyms and len(word.synonyms) > 0:
            if word.meaning == word.synonyms[0]:
                needs_fix = True
        
        if len(word.meaning or "") < 5:
            needs_fix = True
        
        if any('\u0980' <= c <= '\u09FF' for c in (word.meaning or "")):
            needs_fix = True
        
        if not needs_fix:
            continue
        
        definition = get_definition(word.word, dictionary)
        
        if definition:
            word.meaning = definition
            fixed += 1
            if fixed <= 10:  # Show first 10
                print(f"[{i+1}] {word.word}: {definition[:60]}...")
        elif word.synonyms:
            word.meaning = f"Similar to: {', '.join(word.synonyms[:3])}"
            fixed += 1
    
    db.commit()
    
    # Show final stats
    all_words = db.query(Vocabulary).all()
    still_broken = 0
    for w in all_words:
        if any('\u0980' <= c <= '\u09FF' for c in (w.meaning or '')):
            still_broken += 1
        elif w.synonyms and w.meaning == w.synonyms[0]:
            still_broken += 1
        elif len(w.meaning or '') < 5:
            still_broken += 1
    
    db.close()
    
    print(f"\nDone! Fixed {fixed} meanings.")
    print(f"Still broken: {still_broken}")


if __name__ == "__main__":
    fix_meanings()
