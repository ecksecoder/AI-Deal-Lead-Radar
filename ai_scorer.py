"""AI and deterministic heuristic scoring engine for AI Deal & Lead Radar."""

import asyncio
import json
import logging
import re
from typing import Any
from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger("radar.ai_scorer")

# Strict timeout in seconds for LLM scoring requests
LLM_TIMEOUT: float = 12.0

VALID_CATEGORIES: set[str] = {"HOT_LEAD", "HIGH_VALUE", "STANDARD", "LOW_PRIORITY"}


def determine_category(score: int) -> str:
    """Map a numerical score (0-100) to an enterprise lead category."""
    if score >= 85:
        return "HOT_LEAD"
    if score >= 70:
        return "HIGH_VALUE"
    if score >= 40:
        return "STANDARD"
    return "LOW_PRIORITY"


def heuristic_score(title: str, snippet: str, keywords: str) -> dict[str, Any]:
    """Deterministic fallback scorer using keyword density, regex heuristics, and budget detection.

    Args:
        title: Item title.
        snippet: Raw textual snippet or item description.
        keywords: User-defined filter criteria (comma or space separated).

    Returns:
        Structured scoring dictionary with score, category, and 2-sentence Russian summary.
    """
    combined = f"{title} {snippet}".lower()
    title_lower = title.lower()

    # Parse and clean keywords
    keyword_terms = [k.strip().lower() for k in re.split(r"[,;|\n]+", keywords) if k.strip()]

    matched_keywords: list[str] = []
    title_matches: list[str] = []
    for term in keyword_terms:
        if term in combined:
            matched_keywords.append(term)
        if term in title_lower:
            title_matches.append(term)

    # Base scoring baseline
    if keyword_terms:
        score = 50 + (len(matched_keywords) * 12) + (len(title_matches) * 8)
        if not matched_keywords:
            score = 25
    else:
        score = 65

    # Budget & financial signal detection
    budget_pattern = re.compile(
        r"(\$\s*[\d,]+|[\d,]+\s*\$|[\d,]+\s*(?:usd|eur|€|руб|тыс|k|к)|"
        r"бюджет[:\s]*[\d,]+|фиксированн\w+\s+оплат\w+|ставка[:\s]*[\d,]+)",
        re.IGNORECASE,
    )
    budget_match = budget_pattern.search(f"{title} {snippet}")
    detected_budget = budget_match.group(0).strip() if budget_match else ""

    if detected_budget:
        score += 15

    # Enterprise / urgency terms
    urgency_pattern = re.compile(
        r"\b(enterprise|senior|lead|срочно|urgent|контракт|тендер|ai|llm|агент|radar|automation|автоматизация|b2b)\b",
        re.IGNORECASE,
    )
    if urgency_pattern.search(combined):
        score += 10

    # Negative / low-value terms
    negative_pattern = re.compile(
        r"\b(бесплатно|стажировка|практика|volunteer|internship|за отзыв|бартер|студент)\b",
        re.IGNORECASE,
    )
    if negative_pattern.search(combined):
        score -= 30

    score = max(0, min(100, score))
    category = determine_category(score)

    # Generate 2-sentence Russian summary highlighting budget/value and key action
    if detected_budget:
        sent1 = (
            f"Высокорелевантный проект с подтверждённым бюджетом ({detected_budget}) "
            f"и совпадением по ключевым требованиям."
        )
    elif matched_keywords:
        matched_str = ", ".join(matched_keywords[:3])
        sent1 = f"Лид соответствует целевым критериям поиска ({matched_str}) с потенциалом долгосрочного контракта."
    else:
        sent1 = "Предложение содержит профильные задачи в сфере B2B автоматизации и разработки."

    if category in ("HOT_LEAD", "HIGH_VALUE"):
        sent2 = "Рекомендуется немедленно откликнуться и запросить вводный созвон с заказчиком."
    elif category == "STANDARD":
        sent2 = "Рекомендуется провести экспресс-оценку трудозатрат и направить типовое коммерческое предложение."
    else:
        sent2 = "Рекомендуется отложить в архив или мониторить изменения условий проекта."

    summary = f"{sent1} {sent2}"

    return {
        "score": score,
        "category": category,
        "summary": summary,
    }


def _call_gemini_sync(title: str, snippet: str, keywords: str) -> dict[str, Any]:
    """Execute synchronous Google Gemini API scoring call."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""You are an elite B2B deal analyst and lead scoring engine.
Evaluate the following lead item against the user's target keywords and business criteria.

TARGET KEYWORDS / CRITERIA:
{keywords or "B2B software, automation, Python development, scraping, AI agents"}

LEAD TITLE:
{title}

LEAD SNIPPET:
{snippet}

Respond STRICTLY with a valid JSON object with the following schema:
{{
  "score": <integer from 0 to 100>,
  "category": "<HOT_LEAD | HIGH_VALUE | STANDARD | LOW_PRIORITY>",
  "summary": "<Exactly 2 concise sentences in Russian highlighting the detected budget/value and recommended next action>"
}}

Guidelines for category:
- HOT_LEAD: 85-100 (explicit budget, urgent, enterprise client, exact tech match)
- HIGH_VALUE: 70-84 (strong match, good scope, solvent client)
- STANDARD: 40-69 (moderate match, small budget or partial scope)
- LOW_PRIORITY: 0-39 (irrelevant, unverified, internship, barter, or no budget)
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )

    raw_text = response.text or ""
    data = json.loads(raw_text)

    score_val = int(data.get("score", 50))
    score_val = max(0, min(100, score_val))

    cat_val = str(data.get("category", "")).strip().upper()
    if cat_val not in VALID_CATEGORIES:
        cat_val = determine_category(score_val)

    summary_val = str(data.get("summary", "")).strip()
    if not summary_val:
        summary_val = "Проект проанализирован нейросетью. Рекомендуется изучить детальные условия."

    return {
        "score": score_val,
        "category": cat_val,
        "summary": summary_val,
    }


async def score_item(title: str, snippet: str, keywords: str = "") -> dict[str, Any]:
    """Score a lead item using Google Gemini LLM with automatic heuristic fallback.

    Args:
        title: Item title.
        snippet: Raw snippet or description.
        keywords: User criteria and keywords.

    Returns:
        Dictionary with 'score', 'category', and 'summary'.
    """
    if not GEMINI_API_KEY:
        return heuristic_score(title, snippet, keywords)

    try:
        scoring_task = asyncio.to_thread(_call_gemini_sync, title, snippet, keywords)
        return await asyncio.wait_for(scoring_task, timeout=LLM_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("Gemini LLM scoring timed out after %.1fs. Falling back to heuristic.", LLM_TIMEOUT)
        return heuristic_score(title, snippet, keywords)
    except Exception as exc:
        logger.warning(
            "Gemini LLM scoring failed (%s: %s). Falling back to deterministic heuristic.",
            type(exc).__name__,
            exc,
        )
        return heuristic_score(title, snippet, keywords)
