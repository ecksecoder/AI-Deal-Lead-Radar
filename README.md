# AI Deal & Lead Radar (Enterprise Monitoring & AI Scoring System)

Production-ready, asynchronous B2B deal monitoring, web-scraping, and AI-scoring system equipped with an interactive Telegram control panel (`aiogram 3.x`), SQLite WAL deduplication engine, and automated Excel-compatible reporting with UTF-8 BOM.

---

## Key Capabilities

- **Zero-Config Portfolio Demo:** Immediate out-of-the-box `/demo` command and interactive button simulating ingestion of 3 realistic B2B projects, running AI scoring, and rendering Telegram Micro-CRM cards.
- **Multimodal Source Ingestion:** Supports RSS/Atom feeds, generic HTML listings (articles, jobs, tenders), JSON APIs, and internal demo generators with SSRF protection.
- **Deterministic Deduplication:** SHA-256 content hashing in SQLite WAL mode prevents duplicate notifications.
- **Dual-Engine AI Scoring:**
  - **Google Gemini Engine:** Evaluates opportunities against target criteria using `gemini-3.8-flash` via the official `google-genai` SDK.
  - **Resilient Heuristic Fallback:** If API quota is exhausted or `GEMINI_API_KEY` is omitted, the system falls back to keyword-density, budget-detection, and regex heuristics without interrupting background operations.
- **Interactive Telegram Control Panel:** Built on `aiogram 3.x` with inline source management (toggle pause/run, check now, delete) and Micro-CRM actions (`⭐ В избранное`, `📥 В архив`, `🔗 Открыть источник`).
- **Excel-Compatible Reporting:** Generates `.csv` exports with UTF-8 BOM (`\xef\xbb\xbf`) and semicolon (`;`) delimiter, ensuring Cyrillic text and numbers open natively in Microsoft Excel without broken encoding.

---

## Architecture & Code Structure

The project strictly follows a flat, modular architecture (6 core Python modules):

```
project_3/
├── .env.example        # Environment variable template
├── .gitignore           # Git exclusions (.env, *.db, exports/, __pycache__/)
├── requirements.txt     # Python dependencies
├── README.md            # System documentation
├── config.py            # Environment validation, constants, and SSRF filter
├── database.py          # Asynchronous SQLite WAL manager (asyncio.to_thread)
├── scraper.py           # aiohttp client, retry backoff, RSS/HTML/JSON parsers
├── ai_scorer.py         # Google Gemini SDK scoring + deterministic heuristic fallback
├── exporter.py          # Excel-friendly CSV generator (UTF-8-SIG BOM)
└── bot.py               # aiogram 3.x dispatcher, FSM wizard, background worker
```

---

## Quickstart

### 1. Prerequisites
- Python 3.10+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Optional: Google Gemini API Key

### 2. Installation
```bash
git clone <YOUR_REPOSITORY_URL>
cd project_3

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and fill in your parameters:
```bash
cp .env.example .env
```

```ini
# Required: Bot token from @BotFather
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ

# Required: Authorized Telegram user IDs (comma-separated integers)
ADMIN_IDS=123456789

# Optional: Google Gemini API key (defaults to deterministic heuristic if omitted)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash

# Radar parameters
POLL_INTERVAL_SECONDS=300
HTTP_TIMEOUT=15.0
MIN_ALERT_SCORE=60
```

### 4. Launching the System
```bash
python bot.py
```

---

## Bot Commands & User Flows

| Command / Button | Description |
|---|---|
| `/start` | Displays executive dashboard: active sources, total analyzed, hot leads, saved items. |
| `⚡ Демо-прогон (Тест радара)` / `/demo` | Triggers immediate demo ingestion of 3 realistic leads, scores them, and displays interactive cards. |
| `📡 Мои источники` / `/sources` | Lists configured sources with inline controls: `[⏸ Пауза]`, `[🔄 Проверить]`, `[🗑 Удалить]`. |
| `➕ Добавить источник` / `/add` | Interactive 4-step FSM wizard to add an RSS feed, HTML page, or Demo source. |
| `📊 Скачать отчёт (Excel/CSV)` / `/export` | Generates and sends a downloadable `.csv` file ready for Microsoft Excel. |

---

## Testing & Verification

Compile and test all modules:
```bash
# 1. Syntax & compilation check
python -m py_compile config.py database.py scraper.py ai_scorer.py exporter.py bot.py

# 2. Run automated verification suite
python -c "import asyncio, database; asyncio.run(database.init_db())"
```
