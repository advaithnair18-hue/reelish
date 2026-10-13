"""Turn messy video text (caption + transcript) into a structured recipe.

Two extractors share one interface:
- ClaudeExtractor: asks an LLM for JSON, then validates it. Used when ANTHROPIC_API_KEY is set.
- RuleBasedExtractor: regex parsing. Works offline, keeps tests deterministic,
  and is the fallback when the LLM call fails.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel, Field, ValidationError

from ..config import settings
from .units import UNIT_ALIASES

log = logging.getLogger(__name__)


@dataclass
class ExtractedIngredient:
    name: str
    quantity: str = ""  # kept as text; units.parse_quantity turns it into a Decimal
    unit: str = ""
    raw_text: str = ""


@dataclass
class ExtractedRecipe:
    title: str
    servings: int | None = None
    ingredients: list[ExtractedIngredient] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)


class ExtractionError(Exception):
    pass


# ---------------------------------------------------------------- rule-based

_UNITS = sorted(UNIT_ALIASES, key=len, reverse=True)
_UNIT_RE = "|".join(re.escape(u) for u in _UNITS)
_NUM = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?\s*[½⅓⅔¼¾⅛]?|[½⅓⅔¼¾⅛])"
_WORDNUM = r"(?:a half|a quarter|half|an|a|one|two|three|four|five|six|seven|eight|ten|twelve)"
_QTY = rf"(?P<qty>{_NUM}(?:\s*(?:-|–|to)\s*{_NUM})?|{_WORDNUM})"

# A caption line: "- 2 cups flour", "1/2 tsp salt", "3 garlic cloves, minced"
_LINE_RE = re.compile(
    rf"^\s*(?:[-•*▪️✅🔸]\s*)?{_QTY}\s*(?:(?P<unit>{_UNIT_RE})\.?\b\s*)?(?:of\s+)?(?P<name>[A-Za-z][^\n]{{1,80}})$",
    re.IGNORECASE,
)
# Inside speech: "add two cups of flour", "a pinch of salt"
_SPOKEN_RE = re.compile(
    rf"\b{_QTY}\s+(?P<unit>{_UNIT_RE})\b\.?\s*(?:of\s+)?(?P<name>[a-z][a-z' -]{{1,40}}?)"
    r"(?=\s+(?:and|then|in|into|to|with|for)\b|[,.;!?]|$)",
    re.IGNORECASE,
)
_NOT_INGREDIENTS = {"minute", "minutes", "hour", "hours", "second", "seconds", "degree", "degrees",
                    "bowl", "pan", "pot", "oven", "time", "times", "serving", "servings", "people",
                    "day", "days", "week", "few", "lot", "bit", "little", "while", "video", "recipe"}
_STEP_VERBS = re.compile(r"\b(add|mix|stir|bake|cook|fry|boil|simmer|whisk|chop|dice|slice|pour|"
                         r"combine|season|serve|heat|preheat|roast|blend|fold|marinate|toss|top)\b", re.I)


class RuleBasedExtractor:
    def extract(self, caption: str, transcript: str) -> ExtractedRecipe:
        ingredients: list[ExtractedIngredient] = []
        seen: set[str] = set()

        def add(qty: str, unit: str | None, name: str, raw: str) -> None:
            name = re.sub(r"\s+", " ", name).strip(" .,-:;")
            first = name.lower().split()[0] if name else ""
            if not name or first in _NOT_INGREDIENTS or len(name.split()) > 8:
                return
            key = f"{qty}|{unit}|{name.lower()}"
            if key in seen:
                return
            seen.add(key)
            ingredients.append(ExtractedIngredient(name=name, quantity=qty.strip(), unit=unit or "",
                                                   raw_text=raw.strip()))

        caption_lines = [line.strip() for line in caption.splitlines() if line.strip()]
        for line in caption_lines:
            if line.startswith("#"):
                continue
            m = _LINE_RE.match(line)
            if m and not re.match(r"^\d+[.)]\s", line):  # "1. Preheat oven" is a step, not 1 preheat
                add(m["qty"], m["unit"], m["name"], line)

        for m in _SPOKEN_RE.finditer(transcript):
            add(m["qty"], m["unit"], m["name"], m.group(0))

        return ExtractedRecipe(
            title=self._title(caption_lines, transcript),
            servings=self._servings(caption + " " + transcript),
            ingredients=ingredients,
            steps=self._steps(caption_lines, transcript),
        )

    @staticmethod
    def _title(lines: list[str], transcript: str) -> str:
        for line in lines:
            clean = re.sub(r"#\w+|\(?\b(?:serves|servings?:?)\s*\d+\)?", "", line, flags=re.I).strip(" -:!|·")
            if clean and not _LINE_RE.match(line) and not re.match(r"^\d+[.)]", line) \
                    and not clean.lower().startswith(("ingredients", "method", "steps", "instructions")):
                return clean[:80]
        first = re.split(r"[.!?]", transcript.strip(), maxsplit=1)[0].strip()
        return first[:80] if first else "Untitled recipe"

    @staticmethod
    def _servings(text: str) -> int | None:
        m = re.search(r"\b(?:serves|servings?:?)\s*(\d+)|\b(\d+)\s+servings\b", text, re.I)
        if not m:
            return None
        return int(m.group(1) or m.group(2))

    @staticmethod
    def _steps(lines: list[str], transcript: str) -> list[str]:
        numbered = [re.sub(r"^(?:step\s*)?\d+[.):]\s*", "", line, flags=re.I)
                    for line in lines if re.match(r"^(?:step\s*)?\d+[.):]\s+\D", line, re.I)]
        if numbered:
            return numbered
        sentences = re.split(r"(?<=[.!?])\s+", transcript.strip())
        return [s.strip() for s in sentences if _STEP_VERBS.search(s)][:15]


# ---------------------------------------------------------------- LLM-based

class _LLMIngredient(BaseModel):
    name: str = Field(min_length=1)
    quantity: str | float | int | None = ""
    unit: str | None = ""
    raw_text: str | None = ""


class _LLMRecipe(BaseModel):
    title: str = Field(min_length=1)
    servings: int | None = None
    ingredients: list[_LLMIngredient]
    steps: list[str] = []


PROMPT = """You extract recipes from short cooking videos (TikTok / Instagram Reels).
Below are the video's caption and an automatic speech transcript. Either may be empty,
noisy, or contain chatter unrelated to cooking.

Return ONLY a JSON object, no prose, matching:
{{"title": str, "servings": int | null,
  "ingredients": [{{"name": str, "quantity": str, "unit": str, "raw_text": str}}],
  "steps": [str]}}

Rules:
- name: what you would buy, without preparation words ("onion", not "diced onion").
- quantity: a number or fraction as text ("1/2", "2"); "" if not stated. Never guess amounts.
- unit: e.g. "cup", "tbsp", "tsp", "g", "ml", "clove", "can"; "" for countable items.
- raw_text: the words the amount came from.
- Only include ingredients actually mentioned. Do not invent any.

<caption>
{caption}
</caption>
<transcript>
{transcript}
</transcript>"""


class ClaudeExtractor:
    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=60)

    def extract(self, caption: str, transcript: str) -> ExtractedRecipe:
        resp = self.client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": self.model, "max_tokens": 2000,
                  "messages": [{"role": "user", "content": PROMPT.format(
                      caption=caption[:8000], transcript=transcript[:20000])}]},
        )
        if resp.status_code != 200:
            raise ExtractionError(f"LLM request failed with HTTP {resp.status_code}")
        text = "".join(block.get("text", "") for block in resp.json().get("content", []))
        return parse_llm_json(text)


def parse_llm_json(text: str) -> ExtractedRecipe:
    """Validate the model's output. Models sometimes wrap JSON in prose or code fences."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ExtractionError("No JSON object in model output")
    try:
        data = _LLMRecipe.model_validate(json.loads(text[start:end + 1]))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ExtractionError(f"Model output failed validation: {exc}") from exc
    return ExtractedRecipe(
        title=data.title.strip()[:255],
        servings=data.servings,
        ingredients=[ExtractedIngredient(name=i.name.strip(),
                                         quantity="" if i.quantity is None else str(i.quantity),
                                         unit=i.unit or "", raw_text=i.raw_text or "")
                     for i in data.ingredients],
        steps=[s.strip() for s in data.steps if s.strip()],
    )


def extract_recipe(caption: str, transcript: str) -> ExtractedRecipe:
    """Use the LLM when configured; fall back to rules if it fails."""
    if settings.anthropic_api_key:
        try:
            return ClaudeExtractor(settings.anthropic_api_key, settings.anthropic_model).extract(
                caption, transcript)
        except (ExtractionError, httpx.HTTPError) as exc:
            log.warning("LLM extraction failed, falling back to rules: %s", exc)
    return RuleBasedExtractor().extract(caption, transcript)
