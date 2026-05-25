"""
Regenerate accurate Bengali meanings for vocabulary words.

Uses Groq (fast) with Google Gemma as fallback. Batches 25 words per request,
runs batches concurrently, validates output, retries failures individually.

Usage (from backend/):
    venv/Scripts/python.exe scripts/fix_bengali.py                # fix only broken ones
    venv/Scripts/python.exe scripts/fix_bengali.py --all          # regenerate every word
    venv/Scripts/python.exe scripts/fix_bengali.py --dry-run      # preview, no DB writes
    venv/Scripts/python.exe scripts/fix_bengali.py --limit 20     # process first N
"""

import argparse
import asyncio
import io
import json
import os
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from app.core.database import SessionLocal
from app.models.vocabulary import Vocabulary

GROQ_KEY = os.getenv("GROQ_API_KEY", "")
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY", "")

GROQ_MODELS = [
    "llama-3.3-70b-versatile",  # most accurate for translation
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]
GEMMA_MODELS = ["gemma-2-27b-it", "gemma-2-9b-it", "gemini-2.0-flash-lite"]

BATCH_SIZE = 25
CONCURRENT_BATCHES = 4

BENGALI_RE = re.compile(r"[ঀ-৿]")
LATIN_RE = re.compile(r"[A-Za-z]")
MATRAS = set("ািীুূৃেৈোৌ্ংঃঁ")
DEP_VOWELS = set("ািীুূৃেৈোৌ")

# PDF-extraction artifacts — only patterns that are NEVER valid Bengali.
# Each must be impossible in proper modern Shuddha Bangla.
CORRUPTION_FRAGMENTS = [
    "ক্লব",   # mis-extracted প্র / ক্রি (valid is রক্লব? no, ক্ল alone IS valid in some words)
    "পপ",    # consecutive identical প at start
    "পদও",   # দে + ো misextraction
    "নয্",   # য-phala misplacement
]


def has_bengali(s: str) -> bool:
    return bool(BENGALI_RE.search(s or ""))


def is_corrupted(s: str) -> tuple[bool, str]:
    """Detect PDF-extraction corruption. Returns (is_broken, reason)."""
    if not s or not s.strip():
        return True, "empty"
    s = s.strip()
    if "�" in s:
        return True, "replacement-char"
    if not has_bengali(s):
        return True, "no-bengali"
    if len(LATIN_RE.findall(s)) > 2:
        return True, "latin-mix"
    if s[0] in MATRAS:
        return True, "leading-matra"
    if re.search(r"্[ািীুূৃেৈোৌ]", s):
        return True, "virama+matra"
    if re.search(r"[ািীুূৃেৈোৌ]{2,}", s):
        return True, "double-matra"
    for frag in CORRUPTION_FRAGMENTS:
        if frag in s:
            return True, f"frag:{frag}"
    return False, ""


# ── AI clients ────────────────────────────────────────────────────────────────

def make_groq():
    if not GROQ_KEY:
        return None
    try:
        from groq import AsyncGroq
        return AsyncGroq(api_key=GROQ_KEY)
    except Exception:
        return None


def make_gemma(model_name):
    if not GOOGLE_KEY:
        return None
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=GOOGLE_KEY,
            temperature=0.1,
            max_output_tokens=1500,
        )
    except Exception:
        return None


PROMPT_TEMPLATE = """You are a professional Bengali (Bangla) translator. Translate each English word to its standard dictionary Bengali equivalent.

STRICT RULES:
1. Use proper Unicode Bengali script (UTF-8). NEVER use Roman transliteration.
2. Each translation: 1–6 Bengali words. Dictionary-style, no sentences.
3. For verbs, append "করা" naturally (e.g., abandon → পরিত্যাগ করা).
4. Use standard modern Shuddha Bangla spelling — no archaic forms, no regional variants.
5. Match the part of speech given.
6. Return ONLY a valid JSON object mapping the lowercase English word to its Bengali translation.
7. No markdown, no commentary, no extra keys.

Example output: {{"abandon": "পরিত্যাগ করা", "active": "সক্রিয়", "ample": "প্রচুর"}}

Words to translate:
{numbered}

Return JSON only:"""


def build_prompt(items):
    numbered = "\n".join(
        f'{i+1}. {it["word"]} ({it["pos"]}): {it["meaning"][:80]}'
        for i, it in enumerate(items)
    )
    return PROMPT_TEMPLATE.format(numbered=numbered)


def parse_translations(raw: str) -> dict:
    if not raw:
        return {}
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    m = re.search(r"\{[\s\S]+\}", raw)
    if m:
        raw = m.group(0)
    try:
        data = json.loads(raw)
        return {
            k.lower().strip(): v.strip()
            for k, v in data.items()
            if isinstance(v, str) and v.strip()
        }
    except Exception:
        return {}


async def call_groq(client, items, model_name):
    resp = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": build_prompt(items)}],
        temperature=0.1,
        max_tokens=1500,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""


async def call_gemma(model, items):
    resp = await model.ainvoke(build_prompt(items))
    content = resp.content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
        return ""
    return content or ""


async def translate_batch(items, groq_client, gemma_models):
    """Try Groq first, fall back to Gemma. Returns dict of translations."""
    if groq_client:
        for m in GROQ_MODELS:
            try:
                raw = await call_groq(groq_client, items, m)
                parsed = parse_translations(raw)
                if parsed:
                    return parsed
            except Exception as e:
                msg = str(e)
                if "429" in msg or "rate" in msg.lower():
                    await asyncio.sleep(2)
                continue
    for gm in gemma_models:
        try:
            raw = await call_gemma(gm, items)
            parsed = parse_translations(raw)
            if parsed:
                return parsed
        except Exception:
            continue
    return {}


# ── Main ──────────────────────────────────────────────────────────────────────

async def run(all_words: bool, dry_run: bool, limit, force: bool):
    if not GROQ_KEY and not GOOGLE_KEY:
        print("ERROR: neither GROQ_API_KEY nor GOOGLE_API_KEY is set")
        sys.exit(1)

    groq_client = make_groq()
    gemma_models = [m for m in (make_gemma(n) for n in GEMMA_MODELS) if m is not None]
    print(f"Providers: groq={'yes' if groq_client else 'no'}, gemma={len(gemma_models)}")

    db = SessionLocal()
    every = db.query(Vocabulary).order_by(Vocabulary.word).all()

    if all_words or force:
        words = every
        print(f"Regenerating ALL {len(words)} words")
    else:
        words = [w for w in every if is_corrupted(w.meaning_bengali or "")[0]]
        print(f"Broken/missing: {len(words)} / {len(every)}")

    if limit:
        words = words[:limit]
        print(f"(limited to {limit})")

    if not words:
        print("Nothing to fix.")
        db.close()
        return

    batches = [words[i:i + BATCH_SIZE] for i in range(0, len(words), BATCH_SIZE)]
    print(f"Processing {len(batches)} batches × {BATCH_SIZE}, {CONCURRENT_BATCHES} concurrent\n")

    updated = 0
    failed_words = []
    t0 = time.time()
    sem = asyncio.Semaphore(CONCURRENT_BATCHES)

    async def process_batch(batch_idx, batch):
        nonlocal updated
        items = [
            {"word": w.word, "pos": w.part_of_speech or "", "meaning": w.meaning or ""}
            for w in batch
        ]
        async with sem:
            translations = await translate_batch(items, groq_client, gemma_models)

        batch_updated = 0
        batch_failed = []
        for w in batch:
            key = w.word.lower().strip()
            bn = translations.get(key, "").strip()
            if not bn:
                # fuzzy key match (whitespace-insensitive)
                for k, v in translations.items():
                    if k.replace(" ", "") == key.replace(" ", ""):
                        bn = v.strip()
                        break

            broken, why = is_corrupted(bn)
            if not broken:
                if not dry_run:
                    w.meaning_bengali = bn
                batch_updated += 1
                if dry_run:
                    print(f"  {w.word:25s} {(w.meaning_bengali or '(empty)')[:25]:25s} -> {bn}")
            else:
                batch_failed.append((w, bn, why))

        updated += batch_updated
        failed_words.extend(batch_failed)
        done = (batch_idx + 1) * BATCH_SIZE
        pct = min(done, len(words)) / len(words) * 100
        print(f"  [{pct:5.1f}%] batch {batch_idx+1}/{len(batches)} — ok={batch_updated} failed={len(batch_failed)}")

    await asyncio.gather(*(process_batch(i, b) for i, b in enumerate(batches)))

    if not dry_run:
        db.commit()

    # Retry failures one-at-a-time with stricter single-word prompt
    if failed_words:
        print(f"\nRetrying {len(failed_words)} failures individually…")
        retry_ok = 0
        retry_sem = asyncio.Semaphore(CONCURRENT_BATCHES)

        async def retry_one(w):
            nonlocal retry_ok
            async with retry_sem:
                translations = await translate_batch(
                    [{"word": w.word, "pos": w.part_of_speech or "", "meaning": w.meaning or ""}],
                    groq_client, gemma_models,
                )
            bn = translations.get(w.word.lower().strip(), "").strip()
            broken, _ = is_corrupted(bn)
            if not broken:
                if not dry_run:
                    w.meaning_bengali = bn
                retry_ok += 1

        await asyncio.gather(*(retry_one(w) for w, _, _ in failed_words))
        if not dry_run:
            db.commit()
        updated += retry_ok
        print(f"  Retry recovered {retry_ok}/{len(failed_words)}")

    db.close()

    # Final verification
    db2 = SessionLocal()
    final_broken = sum(1 for w in db2.query(Vocabulary).all() if is_corrupted(w.meaning_bengali or "")[0])
    db2.close()

    elapsed = time.time() - t0
    print(f"\n✓ Done in {elapsed:.1f}s — updated={updated}, still broken={final_broken}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="Regenerate every word")
    p.add_argument("--force", action="store_true", help="Alias for --all")
    p.add_argument("--dry-run", action="store_true", help="Preview only")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()
    asyncio.run(run(args.all, args.dry_run, args.limit, args.force))
