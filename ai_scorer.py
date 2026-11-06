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

CROSS_LINGUAL_KEYWORD_MAP: dict[str, set[str]] = {
    "python": {"python", "питон", "пайтон"},
    "bot": {"bot", "bots", "бот", "боты", "боти", "робот"},
    "scraping": {"scraping", "scraper", "scrape", "парсинг", "парсер", "скрапинг", "скрапер"},
    "automation": {"automation", "automate", "автоматизация", "автоматизація"},
    "ai": {"ai", "llm", "ии", "ші", "нейросеть", "нейромережа", "artificial intelligence"},
    "lead": {"lead", "leads", "лид", "лиды", "лід", "ліди"},
    "tender": {"tender", "tenders", "тендер", "тендеры", "тендери"},
    "freelance": {"freelance", "freelancer", "фриланс", "фріланс"},
    "crm": {"crm", "срм", "amo", "hubspot", "bitrix", "битрикс", "бітрікс"},
    "urgent": {"urgent", "срочно", "терміново"},
    "contract": {"contract", "договор", "контракт", "договір"},
}


def determine_category(score: int) -> str:
    """Map a numerical score (0-100) to an enterprise lead category."""
    if score >= 85:
        return "HOT_LEAD"
    if score >= 70:
        return "HIGH_VALUE"
    if score >= 40:
        return "STANDARD"
    return "LOW_PRIORITY"


def heuristic_score(title: str, snippet: str, keywords: str, lang: str = "en") -> dict[str, Any]:
    """Deterministic fallback scorer using keyword density, regex heuristics, and budget detection.

    Args:
        title: Item title.
        snippet: Raw textual snippet or item description.
        keywords: User-defined filter criteria (comma or space separated).
        lang: Preferred language for output summary ('en', 'uk', 'ru').

    Returns:
        Structured scoring dictionary with score, category, and 2-sentence localized summary.
    """
    clean_lang = (lang or "en").lower().strip()
    if clean_lang not in ("en", "uk", "ru"):
        clean_lang = "en"

    combined = " ".join(f"{title} {snippet}".lower().split())
    title_lower = " ".join(title.lower().split())

    # Parse and clean keywords with whitespace tolerance
    raw_terms = [
        " ".join(k.lower().strip().split())
        for k in re.split(r"[,;|\n]+", keywords)
        if k.strip() and k.strip() != "-"
    ]

    matched_keywords: list[str] = []
    title_matches: list[str] = []

    for term in raw_terms:
        # Check direct substring
        if term in combined:
            matched_keywords.append(term)
        if term in title_lower:
            title_matches.append(term)

        # Cross-lingual semantic matching
        for root_word, aliases in CROSS_LINGUAL_KEYWORD_MAP.items():
            if term == root_word or term in aliases:
                for alias in aliases:
                    if alias in combined and term not in matched_keywords:
                        matched_keywords.append(term)
                    if alias in title_lower and term not in title_matches:
                        title_matches.append(term)

    # Base scoring baseline
    if raw_terms:
        score = 50 + (len(matched_keywords) * 12) + (len(title_matches) * 8)
        if not matched_keywords:
            score = 25
    else:
        score = 65

    # Budget & financial signal detection
    budget_pattern = re.compile(
        r"(\$\s*[\d,]+|[\d,]+\s*\$|[\d,]+\s*(?:usd|eur|€|руб|грн|тыс|тис|k|к)|"
        r"бюджет[:\s]*[\d,]+|фіксован\w+\s+оплат\w+|фиксированн\w+\s+оплат\w+|ставка[:\s]*[\d,]+)",
        re.IGNORECASE,
    )
    budget_match = budget_pattern.search(f"{title} {snippet}")
    detected_budget = budget_match.group(0).strip() if budget_match else ""

    if detected_budget:
        score += 15

    # Enterprise / urgency terms
    urgency_pattern = re.compile(
        r"\b(enterprise|senior|lead|срочно|терміново|urgent|контракт|договір|договор|тендер|ai|llm|агент|radar|automation|автоматизация|автоматизація|b2b)\b",
        re.IGNORECASE,
    )
    if urgency_pattern.search(combined):
        score += 10

    # Negative / low-value terms
    negative_pattern = re.compile(
        r"\b(бесплатно|безкоштовно|стажировка|стажування|практика|volunteer|internship|за отзыв|за відгук|бартер|студент)\b",
        re.IGNORECASE,
    )
    if negative_pattern.search(combined):
        score -= 30

    score = max(0, min(100, score))
    category = determine_category(score)

    # Generate 2-sentence localized summary highlighting budget/value and key action
    if clean_lang == "uk":
        if detected_budget:
            sent1 = f"Високорелевантний проєкт із підтвердженим бюджетом ({detected_budget}) та збігом за ключовими вимогами."
        elif matched_keywords:
            matched_str = ", ".join(matched_keywords[:3])
            sent1 = f"Лід відповідає цільовим критеріям пошуку ({matched_str}) з потенціалом довгострокового контракту."
        else:
            sent1 = "Пропозиція містить профільні завдання у сфері B2B автоматизації та розробки."

        if category in ("HOT_LEAD", "HIGH_VALUE"):
            sent2 = "Рекомендується негайно відгукнутися та узгодити деталі з замовником."
        elif category == "STANDARD":
            sent2 = "Рекомендується провести експрес-оцінку трудовитрат і надіслати типову комерційну пропозицію."
        else:
            sent2 = "Рекомендується відкласти в архів або моніторити оновлення вимог."
    elif clean_lang == "ru":
        if detected_budget:
            sent1 = f"Высокорелевантный проект с подтверждённым бюджетом ({detected_budget}) и совпадением по ключевым требованиям."
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
    else:  # default 'en'
        if detected_budget:
            sent1 = f"High-relevance opportunity with verified budget ({detected_budget}) and strong criteria alignment."
        elif matched_keywords:
            matched_str = ", ".join(matched_keywords[:3])
            sent1 = f"Lead matches target search criteria ({matched_str}) with long-term contract potential."
        else:
            sent1 = "Opportunity features specialized requirements in B2B automation and engineering."

        if category in ("HOT_LEAD", "HIGH_VALUE"):
            sent2 = "Immediate proposal submission and client discovery call strongly recommended."
        elif category == "STANDARD":
            sent2 = "Quick scope estimation and standard commercial proposal submission recommended."
        else:
            sent2 = "Archive or monitor for updated project requirements."

    summary = f"{sent1} {sent2}"

    return {
        "score": score,
        "category": category,
        "summary": summary,
    }


def _call_gemini_sync(title: str, snippet: str, keywords: str, lang: str = "en") -> dict[str, Any]:
    """Execute synchronous Google Gemini API scoring call."""
    from google import genai
    from google.genai import types

    clean_lang = (lang or "en").lower().strip()
    if clean_lang not in ("en", "uk", "ru"):
        clean_lang = "en"

    lang_names = {
        "en": "English",
        "uk": "Ukrainian",
        "ru": "Russian",
    }
    target_lang_name = lang_names.get(clean_lang, "English")

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""You are an elite B2B deal analyst and lead scoring engine.
Evaluate the following lead item against the user's target keywords and business criteria.

TARGET KEYWORDS / CRITERIA:
{keywords or "B2B software, automation, Python development, scraping, AI agents"}

LEAD TITLE:
{title}

LEAD SNIPPET:
{snippet}

CROSS-LINGUAL RELEVANCE INSTRUCTIONS:
Carefully analyze semantic relevance across languages (English, Ukrainian, and Russian).
Keywords in one language MUST match semantically equivalent content in another language:
- For example, English queries for 'scraping', 'bots', or 'automation' match Ukrainian 'парсинг каталогів', 'розробка ботів' and Russian 'автоматизация парсинга'.
- Ukrainian queries like 'тендери' or 'скоринг' match English 'tender monitoring' or Russian 'тендерные закупки'.
- Do NOT downgrade the score simply because the lead content is written in a different language than the keywords.

Respond STRICTLY with a valid JSON object with the following schema:
{{
  "score": <integer from 0 to 100>,
  "category": "<HOT_LEAD | HIGH_VALUE | STANDARD | LOW_PRIORITY>",
  "summary": "<Exactly 2 concise sentences in {target_lang_name} highlighting the detected budget/value and recommended next action>"
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
        fallbacks = {
            "en": "Project analyzed by neural engine. Review detailed scope and requirements.",
            "uk": "Проєкт проаналізовано нейромережею. Рекомендується вивчити детальні умови.",
            "ru": "Проект проанализирован нейросетью. Рекомендуется изучить детальные условия.",
        }
        summary_val = fallbacks.get(clean_lang, fallbacks["en"])

    return {
        "score": score_val,
        "category": cat_val,
        "summary": summary_val,
    }


async def score_item(
    title: str, snippet: str, keywords: str = "", lang: str = "en"
) -> dict[str, Any]:
    """Score a lead item using Google Gemini LLM with automatic heuristic fallback.

    Args:
        title: Item title.
        snippet: Raw snippet or description.
        keywords: User criteria and keywords.
        lang: Target interface language for generated summaries ('en', 'uk', 'ru').

    Returns:
        Dictionary with 'score', 'category', and 'summary'.
    """
    if not GEMINI_API_KEY:
        return heuristic_score(title, snippet, keywords, lang=lang)

    try:
        scoring_task = asyncio.to_thread(_call_gemini_sync, title, snippet, keywords, lang)
        return await asyncio.wait_for(scoring_task, timeout=LLM_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(
            "Gemini LLM scoring timed out after %.1fs. Falling back to heuristic.", LLM_TIMEOUT
        )
        return heuristic_score(title, snippet, keywords, lang=lang)
    except Exception as exc:
        logger.warning(
            "Gemini LLM scoring failed (%s: %s). Falling back to deterministic heuristic.",
            type(exc).__name__,
            exc,
        )
        return heuristic_score(title, snippet, keywords, lang=lang)
