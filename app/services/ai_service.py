import json
import re
from app.core.config import get_settings

settings = get_settings()

# Groq models — fastest first. llama-3.1-8b-instant is ~750 tok/s.
GROQ_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "gemma2-9b-it",
]

# Google Gemma fallback (used only if all Groq attempts fail)
GEMMA_MODELS = [
    "gemma-2-27b-it",
    "gemma-2-9b-it",
    "gemini-2.0-flash-lite",
]


def _strip_json(raw: str) -> str:
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0]
    return raw.strip()


class AIService:
    def __init__(self):
        self.groq_api_key = settings.GROQ_API_KEY
        self.google_api_key = settings.GOOGLE_API_KEY
        self._groq_client = None
        self._gemma_clients = {}

    @property
    def groq_client(self):
        if self._groq_client is not None:
            return self._groq_client
        if not self.groq_api_key:
            return None
        try:
            from groq import AsyncGroq
            self._groq_client = AsyncGroq(api_key=self.groq_api_key)
            return self._groq_client
        except Exception:
            return None

    def _gemma_client(self, model_name: str):
        if model_name in self._gemma_clients:
            return self._gemma_clients[model_name]
        if not self.google_api_key:
            return None
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            m = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=self.google_api_key,
                temperature=0.7,
                max_output_tokens=800,
            )
            self._gemma_clients[model_name] = m
            return m
        except Exception:
            return None

    async def _chat(self, prompt: str, json_mode: bool = False, max_tokens: int = 800) -> str:
        # Try Groq first (fast path)
        client = self.groq_client
        if client:
            for model_name in GROQ_MODELS:
                try:
                    kwargs = {
                        "model": model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7,
                        "max_tokens": max_tokens,
                    }
                    if json_mode:
                        kwargs["response_format"] = {"type": "json_object"}
                    resp = await client.chat.completions.create(**kwargs)
                    text = resp.choices[0].message.content or ""
                    if text:
                        return text
                except Exception:
                    continue

        # Fallback: Google Gemma via langchain
        for model_name in GEMMA_MODELS:
            m = self._gemma_client(model_name)
            if not m:
                continue
            try:
                response = await m.ainvoke(prompt)
                content = response.content
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            return block.get("text", "")
                    return ""
                return content or ""
            except Exception:
                continue
        return ""

    async def generate_bengali_meaning(self, word: str, pos: str, meaning: str) -> str:
        prompt = (
            f'Translate to Bengali (Bangla) unicode — short dictionary entry (1-6 words max).\n'
            f'Word: {word} ({pos})\n'
            f'English meaning: {meaning[:120]}\n\n'
            f'Rules: proper Unicode Bengali script, standard modern spelling, concise.\n'
            f'For verbs include "করা" where natural.\n'
            f'Reply with ONLY the Bengali text, nothing else.'
        )
        result = (await self._chat(prompt, max_tokens=64)).strip()
        if any('ঀ' <= c <= '৿' for c in result):
            result = re.sub(r'^[A-Za-z\s:"\']+', '', result).strip()
            return result
        return ""

    async def generate_explanation(self, word: str, pos: str, synonyms: list, meaning: str) -> dict:
        prompt = f"""Explain the word "{word}" ({pos}) for IELTS students.
Synonyms: {', '.join(synonyms)}
Meaning: {meaning}

Respond in this exact JSON format (no markdown, no extra text):
{{
    "simple_meaning": "Clear explanation in simple English",
    "academic_usage": "How to use in academic/formal writing",
    "common_mistakes": ["mistake1", "mistake2"],
    "synonym_differences": {{"synonym1": "difference1", "synonym2": "difference2"}},
    "real_life_examples": ["example1", "example2", "example3"],
    "tips": ["tip1", "tip2"]
}}"""
        raw = await self._chat(prompt, json_mode=True, max_tokens=800)
        if raw:
            try:
                return json.loads(_strip_json(raw))
            except Exception:
                pass
        return self._fallback_explanation(word, pos, synonyms, meaning)

    async def generate_sentences(self, word: str, pos: str, meaning: str, count: int = 5) -> list:
        prompt = f"""Generate {count} example sentences for "{word}" ({pos}).
Meaning: {meaning}

Return JSON with key "sentences" — an array of objects:
{{"sentences": [
    {{"sentence": "The sentence.", "context": "formal|ielts|casual|band8|collocation", "band_level": 7.0, "collocations": ["collocation1"]}}
]}}

Make sentences progressively more advanced."""
        raw = await self._chat(prompt, json_mode=True, max_tokens=800)
        if raw:
            try:
                data = json.loads(_strip_json(raw))
                if isinstance(data, dict) and "sentences" in data:
                    return data["sentences"]
                if isinstance(data, list):
                    return data
            except Exception:
                pass
        return self._fallback_sentences(word, pos, meaning)

    async def generate_quiz_question(self, word: str, pos: str, meaning: str, synonyms: list) -> dict:
        prompt = f"""Create a multiple choice question for "{word}" ({pos}).
Meaning: {meaning}
Synonyms: {', '.join(synonyms)}

Return JSON (no markdown):
{{
    "question": "What does '{word}' mean?",
    "options": ["correct meaning", "wrong1", "wrong2", "wrong3"],
    "correct_answer": "correct meaning",
    "explanation": "Why this is correct"
}}"""
        raw = await self._chat(prompt, json_mode=True, max_tokens=400)
        if raw:
            try:
                return json.loads(_strip_json(raw))
            except Exception:
                pass
        return self._fallback_quiz(word, meaning, synonyms)

    def _fallback_explanation(self, word, pos, synonyms, meaning):
        return {
            "simple_meaning": meaning,
            "academic_usage": f'"{word}" is commonly used in academic writing as a {pos.lower()}.',
            "common_mistakes": [f"Confusing {word} with similar-sounding words"],
            "synonym_differences": {s: f"Similar to {word} but with subtle differences" for s in synonyms[:2]},
            "real_life_examples": [
                f"The word '{word}' is frequently encountered in academic texts.",
                f"Understanding '{word}' is essential for IELTS preparation.",
            ],
            "tips": [f"Remember '{word}' means: {meaning}"],
        }

    def _fallback_sentences(self, word, pos, meaning):
        return [
            {"sentence": f"The concept of {word} is fundamental to understanding this topic.", "context": "formal", "band_level": 6.5, "collocations": []},
            {"sentence": f"In contemporary society, {word} plays a crucial role in shaping our perspectives.", "context": "ielts", "band_level": 7.0, "collocations": []},
            {"sentence": f"I often think about {word} in my daily life.", "context": "casual", "band_level": 5.5, "collocations": []},
            {"sentence": f"The pervasive influence of {word} has significantly impacted modern discourse.", "context": "band8", "band_level": 8.0, "collocations": ["pervasive influence"]},
            {"sentence": f"This illustrates the importance of {word} in academic contexts.", "context": "collocation", "band_level": 7.0, "collocations": ["illustrates the importance"]},
        ]

    def _fallback_quiz(self, word, meaning, synonyms):
        return {
            "question": f"What does '{word}' mean?",
            "options": [meaning, "A type of food", "A geographical location", "A mathematical concept"],
            "correct_answer": meaning,
            "explanation": f"'{word}' means: {meaning}",
        }


ai_service = AIService()
