# AI Deal and Lead Radar

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-blue.svg)](https://github.com/aiogram/aiogram)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-orange.svg)](https://www.sqlite.org/)
[![BeautifulSoup4](https://img.shields.io/badge/BeautifulSoup4-4.12%2B-green.svg)](https://www.crummy.com/software/BeautifulSoup/)
[![feedparser](https://img.shields.io/badge/feedparser-6.x-brightgreen.svg)](https://github.com/kurtmckee/feedparser)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English] | [Документация на русском](README_RU.md)

Production-grade asynchronous deal monitoring, lead ingestion, and neural relevance scoring system for freelance platforms, procurement portals, and B2B aggregators. Equipped with an interactive Telegram control panel (aiogram 3.x), SQLite WAL deduplication engine, trilingual localization (EN/UK/RU), and automated Excel-compatible reporting with UTF-8 Byte Order Mark (BOM).

---

## Architecture Overview

```
+-----------------------------------------------------------+
| Target Web Sources & RSS Feeds                            |
+-----------------------------------------------------------+
                              |
                              v
+-----------------------------------------------------------+
| Asynchronous Polling Worker                               |
| (aiohttp, feedparser, DOM sanitization, SSRF protection)  |
+-----------------------------------------------------------+
                              |
                              v
+-----------------------------------------------------------+
| Content Hash Deduplication Layer                          |
| (SHA-256 deterministic signatures in SQLite WAL mode)     |
+-----------------------------------------------------------+
                              |
                              v
+-----------------------------------------------------------+
| Relevance Scoring Engine                                  |
| (Normalized keyword matrix, cross-lingual NLP, AI filter) |
+-----------------------------------------------------------+
                              |
                              v
+-----------------------------------------------------------+
| Dispatcher (aiogram 3.x router)                           |
+-----------------------------------------------------------+
                              |
              +---------------+---------------+
              |                               |
              v                               v
+-------------------------------+ +-------------------------------+
| In-Telegram Instant Alerts    | | Export Generation             |
| (Micro-CRM inline actions)    | | (Excel-compatible CSV / BOM)  |
+-------------------------------+ +-------------------------------+
```

Pipeline execution sequence:
Target Web Sources & RSS -> Asynchronous Polling Worker (aiohttp, feedparser, DOM sanitization) -> Content Hash Deduplication Layer (SHA-256 in SQLite WAL) -> Relevance Scoring Engine (Normalized keyword matrix and AI score filter) -> Dispatcher -> In-Telegram Instant Alerts & Export Generation (CSV/XLSX).

---

## Feature Breakdown

- Autonomous Background Scraping: Asynchronous background worker scans registered RSS/Atom feeds, HTML listings, and JSON endpoints with exponential backoff and comprehensive Server-Side Request Forgery (SSRF) validation.
- Zero-Duplicate Hashing: SHA-256 content fingerprints (computed over normalized URL and title strings) prevent redundant processing and guarantee zero duplicate notifications.
- Trilingual UI (GB/UA/RU): Complete native localization across English, Ukrainian, and Russian interfaces. Automatic Telegram client language detection is paired with instant runtime language override via inline controls.
- Strict Onboarding Standards: Users without prior database records encounter an onboarding language selection gate with Latin '(Telegram)' client auto-sync labels.
- Subscriber-Isolated Notification Formatting: The background scheduler resolves each subscriber's language preference individually, rendering lead alert cards, status badges, and inline actions strictly in that subscriber's language.
- Dynamic Localized CSV/Excel Exports: Generates Excel-friendly CSV reports using UTF-8-SIG encoding (BOM prefix) and semicolon delimiters, dynamically rendering column headers (ID, Date, Source, Category, Score, Title, Summary, Status, URL) in the requesting user's language.
- Synthetic Demo Engine: Self-contained generator produces realistic B2B opportunities localized into English, Ukrainian, and Russian for immediate end-to-end testing without external network traffic.

---

## Tech Stack

| Component | Technology | Technical Purpose |
|---|---|---|
| Language | Python 3.10+ | Core asynchronous application runtime |
| Bot Framework | aiogram 3.x | Telegram Bot API integration, FSM wizards, and event routing |
| Database | SQLite 3 (WAL mode) | Persistent state, user settings, sources, and SHA-256 indexes |
| HTTP Client | aiohttp | Non-blocking HTTP/HTTPS transport with SSL context validation |
| Feed Parser | feedparser & BeautifulSoup4 | RSS 2.0 / Atom XML parsing and DOM sanitization |
| AI Scoring | Google Gemini SDK (`google-genai`) | Semantic opportunity evaluation and cross-lingual relevance analysis |
| Heuristic Scorer | Python Regex Engine | Deterministic keyword density, budget regex, and urgency scoring |
| Report Exporter | Python `csv` module | Excel-compatible UTF-8 BOM (`\xef\xbb\xbf`) delimited export |

---

## Setup and Configuration

### Environment Variables

The application is configured using environment variables defined in a `.env` file:

| Variable | Type | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | String | None (Required) | Telegram Bot API token issued by @BotFather. |
| `CHECK_INTERVAL_SECONDS` | Integer | `300` | Background feed polling frequency in seconds. |
| `DEFAULT_SCORE_THRESHOLD` | Integer | `60` | Minimum score threshold (0-100) required to trigger push alerts. |
| `DB_PATH` | String | `radar_state.db` | File path for SQLite database with WAL journal mode. |
| `ADMIN_IDS` | Comma-separated ints | None | Telegram user IDs authorized to access the system (RBAC). |
| `GEMINI_API_KEY` | String | None (Optional) | Google Gemini API key. Defaults to deterministic heuristics if omitted. |
| `GEMINI_MODEL` | String | `gemini-3.8-flash` | Gemini model name used for AI scoring and evaluation. |
| `HTTP_TIMEOUT` | Float | `15.0` | Maximum network request timeout in seconds. |
| `EXPORT_DIR` | String | `exports` | Directory for temporary export artifact generation. |

### Installation

1. Clone repository and initialize virtual environment:
```bash
git clone <repository_url>
cd project_3
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment settings:
```bash
cp .env.example .env
# Edit .env with your credentials
```

4. Launch application:
```bash
python bot.py
```

---

## Testing and Verification

Verify syntax and byte-compilation across all application modules:

```bash
python -m py_compile bot.py scraper.py database.py locales.py
```

Execute database schema initialization check:

```bash
python -c "import asyncio, database; asyncio.run(database.init_db())"
```

---

## License

This project is licensed under the terms of the MIT License.
