"""Asynchronous scraping and feed parsing engine for AI Deal & Lead Radar."""

import asyncio
import hashlib
import json
import logging
from typing import Any
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
import aiohttp
from bs4 import BeautifulSoup
from config import HTTP_TIMEOUT, is_safe_url

logger = logging.getLogger("radar.scraper")

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


def compute_item_hash(url: str, title: str) -> str:
    """Compute a deterministic SHA-256 hash for deduplication.

    Args:
        url: Cleaned item destination URL.
        title: Normalized item title.

    Returns:
        Hexadecimal SHA-256 string.
    """
    normalized = f"{url.strip().lower()}|{title.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _clean_text(html_fragment: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not html_fragment:
        return ""
    soup = BeautifulSoup(html_fragment, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())


async def fetch_url(url: str, max_retries: int = 2) -> str:
    """Fetch URL text asynchronously with exponential backoff and SSRF protection.

    Args:
        url: Target HTTP/HTTPS endpoint.
        max_retries: Number of retry attempts.

    Returns:
        Response body decoded as text.

    Raises:
        ValueError: If the URL fails SSRF safety checks.
        RuntimeError: If all fetch attempts fail.
    """
    safe, reason = is_safe_url(url)
    if not safe:
        raise ValueError(f"SSRF validation blocked request to {url}: {reason}")

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            async with aiohttp.ClientSession(headers=DEFAULT_HEADERS, timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    resp.raise_for_status()
                    return await resp.text(errors="replace")
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                backoff = 0.6 * (2**attempt)
                logger.warning(
                    "Fetch attempt %d failed for %s (%s). Retrying in %.1fs...",
                    attempt + 1,
                    url,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)

    raise RuntimeError(f"Failed to fetch {url} after {max_retries + 1} attempts: {last_error}")


def parse_rss_or_atom(xml_text: str, base_url: str = "") -> list[dict[str, str]]:
    """Parse RSS 2.0 or Atom feeds into normalized lead dictionaries.

    Args:
        xml_text: Raw XML string.
        base_url: Base URL for relative link resolution.

    Returns:
        List of item dictionaries with title, url, raw_snippet, and item_hash.
    """
    items: list[dict[str, str]] = []

    try:
        root = ET.fromstring(xml_text)
        # Check RSS 2.0
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item"):
                title_elem = item.find("title")
                link_elem = item.find("link")
                desc_elem = item.find("description")

                title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                raw_link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                snippet = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""

                if not title and not raw_link:
                    continue

                full_url = urljoin(base_url, raw_link) if base_url else raw_link
                clean_snippet = _clean_text(snippet)
                items.append(
                    {
                        "title": title or "Без названия",
                        "url": full_url,
                        "raw_snippet": clean_snippet,
                        "item_hash": compute_item_hash(full_url, title),
                    }
                )
            if items:
                return items

        # Check Atom
        entries = root.findall("{http://www.w3.org/2005/Atom}entry") or root.findall("entry")
        for entry in entries:
            title_elem = entry.find("{http://www.w3.org/2005/Atom}title") or entry.find("title")
            title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""

            raw_link = ""
            for link_elem in entry.findall("{http://www.w3.org/2005/Atom}link") or entry.findall("link"):
                href = link_elem.attrib.get("href")
                rel = link_elem.attrib.get("rel", "alternate")
                if href and rel == "alternate":
                    raw_link = href
                    break
                if href and not raw_link:
                    raw_link = href

            summary_elem = (
                entry.find("{http://www.w3.org/2005/Atom}summary")
                or entry.find("summary")
                or entry.find("{http://www.w3.org/2005/Atom}content")
                or entry.find("content")
            )
            snippet = summary_elem.text.strip() if summary_elem is not None and summary_elem.text else ""

            if not title and not raw_link:
                continue

            full_url = urljoin(base_url, raw_link) if base_url else raw_link
            clean_snippet = _clean_text(snippet)
            items.append(
                {
                    "title": title or "Без названия",
                    "url": full_url,
                    "raw_snippet": clean_snippet,
                    "item_hash": compute_item_hash(full_url, title),
                }
            )
        if items:
            return items

    except Exception as exc:
        logger.debug("Standard XML ET parser failed (%s), falling back to BeautifulSoup", exc)

    # Fallback to BeautifulSoup parsing
    try:
        soup = BeautifulSoup(xml_text, "html.parser")
        tags = soup.find_all(["item", "entry"])
        for tag in tags:
            title_tag = tag.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""

            link_tag = tag.find("link")
            raw_link = ""
            if link_tag:
                raw_link = link_tag.get("href") or link_tag.get_text(strip=True)

            desc_tag = tag.find(["description", "summary", "content"])
            snippet = desc_tag.get_text(strip=True) if desc_tag else ""

            if not title and not raw_link:
                continue

            full_url = urljoin(base_url, raw_link) if base_url else raw_link
            items.append(
                {
                    "title": title or "Без названия",
                    "url": full_url,
                    "raw_snippet": _clean_text(snippet),
                    "item_hash": compute_item_hash(full_url, title),
                }
            )
    except Exception as exc:
        logger.error("Failed to parse feed with fallback parser: %s", exc)

    return items


def parse_html_listing(html_text: str, base_url: str) -> list[dict[str, str]]:
    """Extract lead items from generic HTML article or job listings.

    Args:
        html_text: Raw HTML markup.
        base_url: Page URL for link resolution.

    Returns:
        Extracted list of candidate items.
    """
    items: list[dict[str, str]] = []
    soup = BeautifulSoup(html_text, "html.parser")

    # Look for common article / card containers
    containers = soup.find_all(
        lambda tag: tag.name in ("article", "div", "li", "section")
        and any(
            cls in " ".join(tag.get("class", [])).lower()
            for cls in ("item", "post", "card", "job", "tender", "listing", "feed-item", "vacancy")
        )
    )

    if not containers:
        containers = soup.find_all("article")

    for container in containers[:30]:
        link_tag = container.find("a")
        if not link_tag or not link_tag.get("href"):
            continue

        raw_href = link_tag.get("href", "").strip()
        if raw_href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        full_url = urljoin(base_url, raw_href)

        header_tag = container.find(["h1", "h2", "h3", "h4"])
        if header_tag:
            title = header_tag.get_text(strip=True)
        else:
            title = link_tag.get_text(strip=True)

        if not title or len(title) < 5:
            continue

        p_tag = container.find("p")
        snippet = p_tag.get_text(strip=True) if p_tag else container.get_text(strip=True)
        # Limit snippet size
        snippet = " ".join(snippet.split()[:80])

        items.append(
            {
                "title": title,
                "url": full_url,
                "raw_snippet": snippet,
                "item_hash": compute_item_hash(full_url, title),
            }
        )

    # If no structured containers were found, fall back to heading links
    if not items:
        for heading in soup.find_all(["h2", "h3"])[:20]:
            link = heading.find("a")
            if not link or not link.get("href"):
                continue
            raw_href = link.get("href", "").strip()
            if raw_href.startswith(("#", "javascript:")):
                continue
            full_url = urljoin(base_url, raw_href)
            title = heading.get_text(strip=True)
            if not title:
                continue
            parent = heading.parent
            p_tag = parent.find("p") if parent else None
            snippet = p_tag.get_text(strip=True) if p_tag else ""
            items.append(
                {
                    "title": title,
                    "url": full_url,
                    "raw_snippet": snippet,
                    "item_hash": compute_item_hash(full_url, title),
                }
            )

    return items


def parse_json_feed(json_text: str, base_url: str = "") -> list[dict[str, str]]:
    """Parse JSON feeds or API responses.

    Args:
        json_text: Raw JSON payload.
        base_url: Base URL for relative link resolution.

    Returns:
        List of extracted item dictionaries.
    """
    items: list[dict[str, str]] = []
    try:
        data = json.loads(json_text)
    except Exception as exc:
        logger.warning("Failed to parse response as JSON: %s", exc)
        return items

    elements: list[Any] = []
    if isinstance(data, list):
        elements = data
    elif isinstance(data, dict):
        for candidate_key in ("items", "data", "results", "posts", "jobs", "leads"):
            val = data.get(candidate_key)
            if isinstance(val, list):
                elements = val
                break
        if not elements:
            elements = [data]

    for elem in elements[:30]:
        if not isinstance(elem, dict):
            continue
        title = (
            elem.get("title")
            or elem.get("name")
            or elem.get("headline")
            or elem.get("subject")
            or ""
        )
        url = (
            elem.get("url")
            or elem.get("link")
            or elem.get("permalink")
            or elem.get("href")
            or ""
        )
        snippet = (
            elem.get("snippet")
            or elem.get("summary")
            or elem.get("description")
            or elem.get("body")
            or elem.get("text")
            or ""
        )

        title_str = str(title).strip()
        url_str = str(url).strip()
        snippet_str = str(snippet).strip()

        if not title_str and not url_str:
            continue

        full_url = urljoin(base_url, url_str) if base_url else url_str
        items.append(
            {
                "title": title_str or "Без названия",
                "url": full_url,
                "raw_snippet": _clean_text(snippet_str),
                "item_hash": compute_item_hash(full_url, title_str),
            }
        )

    return items


def generate_demo_items(keywords: str = "") -> list[dict[str, str]]:
    """Generate realistic B2B freelancer and agency leads for instant portfolio demo.

    Args:
        keywords: Optional filter keywords to adjust lead generation.

    Returns:
        A list of 3 pre-configured realistic lead dictionaries.
    """
    demo_records = [
        {
            "title": "Разработка AI-агента для мониторинга тендеров и скоринга лидов на Python / aiogram / LLM (Бюджет: $4,500)",
            "url": "https://freelance-radar.internal/jobs/enterprise-ai-agent-4500",
            "raw_snippet": (
                "Крупная консалтинговая компания ищет Senior Python разработчика для создания "
                "отказоустойчивой системы мониторинга и скоринга B2B-лидов. Стек: Python, aiogram 3.x, "
                "SQLite WAL, Google Gemini / LLM, aiohttp. Обязателен опыт работы с Telegram-ботами "
                "и парсингом. Срок: 3 недели. Фиксированный бюджет: $4,500."
            ),
        },
        {
            "title": "Автоматизация парсинга каталогов поставщиков и синхронизация остатков Shopify/1C ($2,800)",
            "url": "https://freelance-radar.internal/jobs/ecommerce-supplier-scraper-2800",
            "raw_snippet": (
                "Требуется настроить автоматический сбор цен и остатков с 5 оптовых платформ "
                "поставщиков (HTML/API/XML) с выгрузкой в Excel/CSV и CRM. Необходима защита от блокировок, "
                "ротация прокси и обработка капчи. Бюджет: $2,800, возможна помесячная поддержка."
            ),
        },
        {
            "title": "Интеграция CRM (HubSpot/amoCRM) с Telegram-ботом и вебхуками для отдела продаж ($1,500)",
            "url": "https://freelance-radar.internal/jobs/crm-telegram-webhook-1500",
            "raw_snippet": (
                "Необходимо разработать Telegram-бота для мгновенного информирования менеджеров "
                "о новых сделках, изменениях статусов и экспорта еженедельных аналитических отчётов. "
                "Опыт работы с REST API и асинхронным кодом обязателен. Бюджет: $1,500."
            ),
        },
    ]

    results: list[dict[str, str]] = []
    for item in demo_records:
        h = compute_item_hash(item["url"], item["title"])
        results.append(
            {
                "title": item["title"],
                "url": item["url"],
                "raw_snippet": item["raw_snippet"],
                "item_hash": h,
            }
        )
    return results


async def scrape_source(source: dict[str, Any]) -> list[dict[str, str]]:
    """Scrape and parse an individual source based on its configuration.

    Args:
        source: Source dictionary containing source_type, url, keywords, etc.

    Returns:
        List of parsed lead items with hashes.
    """
    source_type = source.get("source_type", "rss").lower()
    url = source.get("url", "")

    if source_type == "demo" or url.startswith("internal://"):
        return generate_demo_items(source.get("keywords", ""))

    try:
        content = await fetch_url(url)
    except Exception as exc:
        logger.error("Failed to fetch source %s (%s): %s", source.get("name"), url, exc)
        return []

    if source_type == "rss":
        return parse_rss_or_atom(content, base_url=url)
    elif source_type == "html":
        return parse_html_listing(content, base_url=url)
    elif source_type == "json":
        return parse_json_feed(content, base_url=url)
    else:
        # Auto-detect format based on content signature
        stripped = content.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return parse_json_feed(content, base_url=url)
        elif stripped.startswith("<?xml") or "<rss" in stripped or "<feed" in stripped:
            return parse_rss_or_atom(content, base_url=url)
        return parse_html_listing(content, base_url=url)
