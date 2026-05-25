"""
Script to extract vocabulary from PDF and save as JSON.
Run: python scripts/extract_pdf.py
"""
import pdfplumber
import json
import re
import os


def extract_vocabulary(pdf_path: str, output_path: str):
    words = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Skip headers
                skip_patterns = ['IELTS', 'Part of', 'Word ', 'Synonym', 'Meaning',
                               'course by', 'Tutorial', 'Mock', 'Lecture', 'SCAN',
                               'Comprehensive', 'Updated', 'Sheets', 'Standard',
                               'Questions', 'Solutions', 'IELTS VOCABULARY', 'Some Useful']
                if any(skip in line for skip in skip_patterns):
                    continue

                # Skip single letters
                if len(line.strip()) == 1 and line.strip().isalpha():
                    continue

                # Skip page numbers
                if line.strip().isdigit():
                    continue

                # Match: Word POS Synonyms Bengali
                pos_pattern = r'\b(Adjective|Noun|Verb|Adverb)\b'
                pos_match = re.search(pos_pattern, line)

                if pos_match:
                    pos = pos_match.group(1)
                    pos_start = pos_match.start()
                    pos_end = pos_match.end()

                    word_text = line[:pos_start].strip()
                    after_pos = line[pos_end:].strip()

                    # Find Bengali text
                    bengali_match = re.search(r'[\u0980-\u09FF]', after_pos)

                    if bengali_match and word_text:
                        bengali_start = bengali_match.start()
                        synonyms_text = after_pos[:bengali_start].strip()
                        meaning = after_pos[bengali_start:].strip()

                        # Parse synonyms
                        synonyms = re.split(r'[,/]', synonyms_text)
                        synonyms = [s.strip() for s in synonyms if s.strip() and s.strip()[0].isupper()]
                        synonyms = [s for s in synonyms if re.match(r'^[A-Za-z]+', s)]

                        if word_text and synonyms:
                            words.append({
                                'word': word_text,
                                'pos': pos,
                                'synonyms': synonyms,
                                'meaning_bengali': meaning
                            })

    # Remove duplicates
    seen = set()
    unique_words = []
    for w in words:
        key = f"{w['word'].lower()}_{w['pos']}"
        if key not in seen:
            seen.add(key)
            unique_words.append(w)

    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(unique_words, f, ensure_ascii=False, indent=2)

    print(f"Extracted {len(unique_words)} unique words")
    return unique_words


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_path = os.path.join(base_dir, "..", "vocabulary_all.pdf")
    output_path = os.path.join(base_dir, "data", "vocabulary.json")
    extract_vocabulary(pdf_path, output_path)
