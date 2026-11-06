"""Asynchronous SQLite database manager for AI Deal & Lead Radar."""

import asyncio
from datetime import datetime, timezone
import logging
import sqlite3
from typing import Any
from config import DB_PATH

logger = logging.getLogger("radar.database")


def _get_connection() -> sqlite3.Connection:
    """Create and configure a SQLite connection with WAL mode enabled.

    Returns:
        Configured sqlite3.Connection object.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _init_db_sync() -> None:
    """Synchronous database schema initialization."""
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                source_type TEXT NOT NULL,
                keywords TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                last_checked_at TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                item_hash TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                raw_snippet TEXT,
                ai_score INTEGER NOT NULL DEFAULT 0,
                ai_category TEXT NOT NULL DEFAULT 'STANDARD',
                ai_summary TEXT,
                status TEXT NOT NULL DEFAULT 'NEW',
                created_at TEXT NOT NULL,
                FOREIGN KEY (source_id) REFERENCES sources (id) ON DELETE CASCADE
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_hash ON items(item_hash);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_score ON items(ai_score);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id TEXT UNIQUE,
                user_id INTEGER,
                source_id INTEGER,
                item_hash TEXT,
                title TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                raw_snippet TEXT DEFAULT '',
                ai_score INTEGER NOT NULL DEFAULT 0,
                ai_category TEXT NOT NULL DEFAULT 'STANDARD',
                ai_summary TEXT DEFAULT '',
                status TEXT DEFAULT 'new',
                created_at TEXT NOT NULL,
                exported_at TIMESTAMP DEFAULT NULL,
                FOREIGN KEY (source_id) REFERENCES sources (id) ON DELETE CASCADE
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_user ON leads(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_lead_id ON leads(lead_id);")

        cursor.execute("PRAGMA table_info(leads);")
        leads_cols = [row["name"] for row in cursor.fetchall()]
        if "status" not in leads_cols:
            cursor.execute("ALTER TABLE leads ADD COLUMN status TEXT DEFAULT 'new';")
        if "exported_at" not in leads_cols:
            cursor.execute("ALTER TABLE leads ADD COLUMN exported_at TIMESTAMP DEFAULT NULL;")
        if "user_id" not in leads_cols:
            cursor.execute("ALTER TABLE leads ADD COLUMN user_id INTEGER;")
        if "lead_id" not in leads_cols:
            cursor.execute("ALTER TABLE leads ADD COLUMN lead_id TEXT;")
        if "source_id" not in leads_cols:
            cursor.execute("ALTER TABLE leads ADD COLUMN source_id INTEGER;")
        if "title" not in leads_cols:
            cursor.execute("ALTER TABLE leads ADD COLUMN title TEXT;")
        if "url" not in leads_cols:
            cursor.execute("ALTER TABLE leads ADD COLUMN url TEXT;")
        if "raw_snippet" not in leads_cols:
            cursor.execute("ALTER TABLE leads ADD COLUMN raw_snippet TEXT;")
        if "ai_score" not in leads_cols:
            cursor.execute("ALTER TABLE leads ADD COLUMN ai_score INTEGER DEFAULT 0;")
        if "ai_category" not in leads_cols:
            cursor.execute("ALTER TABLE leads ADD COLUMN ai_category TEXT DEFAULT 'STANDARD';")
        if "ai_summary" not in leads_cols:
            cursor.execute("ALTER TABLE leads ADD COLUMN ai_summary TEXT;")
        if "created_at" not in leads_cols:
            cursor.execute("ALTER TABLE leads ADD COLUMN created_at TEXT;")

        cursor.execute("PRAGMA table_info(items);")
        items_cols = [row["name"] for row in cursor.fetchall()]
        if "exported_at" not in items_cols:
            cursor.execute("ALTER TABLE items ADD COLUMN exported_at TIMESTAMP DEFAULT NULL;")

        # Populate leads from existing items if leads table is empty
        cursor.execute("SELECT COUNT(*) as count FROM leads;")
        if cursor.fetchone()["count"] == 0:
            cursor.execute(
                """
                INSERT OR IGNORE INTO leads (
                    id, lead_id, user_id, source_id, item_hash, title, url, raw_snippet,
                    ai_score, ai_category, ai_summary, status, created_at
                )
                SELECT i.id, CAST(i.id AS TEXT), s.user_id, i.source_id, i.item_hash, i.title, i.url, i.raw_snippet,
                       i.ai_score, i.ai_category, i.ai_summary,
                       CASE WHEN LOWER(i.status) = 'saved' THEN 'bookmarked'
                            WHEN LOWER(i.status) = 'archived' THEN 'ignored'
                            ELSE 'new' END,
                       i.created_at
                FROM items i
                LEFT JOIN sources s ON i.source_id = s.id;
                """
            )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT NULL
            );
            """
        )
        cursor.execute("PRAGMA table_info(user_settings);")
        user_settings_cols = [row["name"] for row in cursor.fetchall()]
        if "language" not in user_settings_cols:
            cursor.execute("ALTER TABLE user_settings ADD COLUMN language TEXT DEFAULT NULL;")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT NULL
            );
            """
        )
        cursor.execute("PRAGMA table_info(users);")
        user_cols = [row["name"] for row in cursor.fetchall()]
        if "language" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT NULL;")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT NULL
            );
            """
        )
        cursor.execute("PRAGMA table_info(settings);")
        settings_cols = [row["name"] for row in cursor.fetchall()]
        if "language" not in settings_cols:
            cursor.execute("ALTER TABLE settings ADD COLUMN language TEXT DEFAULT NULL;")

        conn.commit()
    logger.info("Database schema initialized with WAL mode.")


async def init_db() -> None:
    """Initialize database tables asynchronously."""
    await asyncio.to_thread(_init_db_sync)


def _add_source_sync(
    user_id: int, name: str, url: str, source_type: str, keywords: str
) -> int:
    now_iso = datetime.now(timezone.utc).isoformat()
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sources (user_id, name, url, source_type, keywords, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (user_id, name.strip(), url.strip(), source_type.strip(), keywords.strip(), now_iso),
        )
        conn.commit()
        return int(cursor.lastrowid)


async def add_source(
    user_id: int, name: str, url: str, source_type: str, keywords: str
) -> int:
    """Add a new monitoring source.

    Returns:
        The primary key ID of the newly created source.
    """
    return await asyncio.to_thread(_add_source_sync, user_id, name, url, source_type, keywords)


def _get_user_sources_sync(user_id: int) -> list[dict[str, Any]]:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, user_id, name, url, source_type, keywords, is_active, last_checked_at, created_at
            FROM sources
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


async def get_user_sources(user_id: int) -> list[dict[str, Any]]:
    """Retrieve all configured sources for a user."""
    return await asyncio.to_thread(_get_user_sources_sync, user_id)


def _get_active_sources_sync() -> list[dict[str, Any]]:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, user_id, name, url, source_type, keywords, is_active, last_checked_at, created_at
            FROM sources
            WHERE is_active = 1
            ORDER BY id ASC
            """
        )
        return [dict(row) for row in cursor.fetchall()]


async def get_active_sources() -> list[dict[str, Any]]:
    """Retrieve all globally active sources for background monitoring."""
    return await asyncio.to_thread(_get_active_sources_sync)


def _get_source_by_id_sync(source_id: int) -> dict[str, Any] | None:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, user_id, name, url, source_type, keywords, is_active, last_checked_at, created_at
            FROM sources
            WHERE id = ?
            """,
            (source_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


async def get_source_by_id(source_id: int) -> dict[str, Any] | None:
    """Retrieve a single source by its ID."""
    return await asyncio.to_thread(_get_source_by_id_sync, source_id)


def _toggle_source_sync(source_id: int) -> bool:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM sources WHERE id = ?", (source_id,))
        row = cursor.fetchone()
        if not row:
            return False
        new_state = 0 if row["is_active"] == 1 else 1
        cursor.execute("UPDATE sources SET is_active = ? WHERE id = ?", (new_state, source_id))
        conn.commit()
        return bool(new_state)


async def toggle_source(source_id: int) -> bool:
    """Toggle source activation status.

    Returns:
        The new active status (True if active, False if paused).
    """
    return await asyncio.to_thread(_toggle_source_sync, source_id)


def _delete_source_sync(source_id: int) -> bool:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        conn.commit()
        return cursor.rowcount > 0


async def delete_source(source_id: int) -> bool:
    """Delete a monitoring source and cascade delete associated items."""
    return await asyncio.to_thread(_delete_source_sync, source_id)


def _update_source_checked_sync(source_id: int) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sources SET last_checked_at = ? WHERE id = ?",
            (now_iso, source_id),
        )
        conn.commit()


async def update_source_checked(source_id: int) -> None:
    """Update the last_checked_at timestamp for a source."""
    await asyncio.to_thread(_update_source_checked_sync, source_id)


def _is_item_seen_sync(item_hash: str) -> bool:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM items WHERE item_hash = ?", (item_hash,))
        return cursor.fetchone() is not None


async def is_item_seen(item_hash: str) -> bool:
    """Check if an item with the given hash has already been stored."""
    return await asyncio.to_thread(_is_item_seen_sync, item_hash)


def _save_item_sync(
    source_id: int,
    item_hash: str,
    title: str,
    url: str,
    raw_snippet: str,
    ai_score: int,
    ai_category: str,
    ai_summary: str,
    status: str,
    lead_id: str | None = None,
) -> int:
    now_iso = datetime.now(timezone.utc).isoformat()
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO items (
                source_id, item_hash, title, url, raw_snippet,
                ai_score, ai_category, ai_summary, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                item_hash,
                title.strip(),
                url.strip(),
                raw_snippet.strip() if raw_snippet else "",
                ai_score,
                ai_category,
                ai_summary.strip() if ai_summary else "",
                status,
                now_iso,
            ),
        )
        item_id = int(cursor.lastrowid)

        # Retrieve user_id from source
        cursor.execute("SELECT user_id FROM sources WHERE id = ?", (source_id,))
        s_row = cursor.fetchone()
        user_id = s_row["user_id"] if s_row else None

        lead_status = "new"
        if status:
            s_clean = status.lower()
            if s_clean in ("saved", "bookmarked"):
                lead_status = "bookmarked"
            elif s_clean in ("archived", "ignored"):
                lead_status = "ignored"

        assigned_lead_id = lead_id or str(item_id)
        cursor.execute(
            """
            INSERT INTO leads (
                id, lead_id, user_id, source_id, item_hash, title, url, raw_snippet,
                ai_score, ai_category, ai_summary, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lead_id) DO UPDATE SET
                title = excluded.title,
                url = excluded.url,
                ai_score = excluded.ai_score,
                ai_category = excluded.ai_category,
                ai_summary = excluded.ai_summary
            """,
            (
                item_id,
                assigned_lead_id,
                user_id,
                source_id,
                item_hash,
                title.strip(),
                url.strip(),
                raw_snippet.strip() if raw_snippet else "",
                ai_score,
                ai_category,
                ai_summary.strip() if ai_summary else "",
                lead_status,
                now_iso,
            ),
        )
        conn.commit()
        return item_id


async def save_item(
    source_id: int,
    item_hash: str,
    title: str,
    url: str,
    raw_snippet: str,
    ai_score: int,
    ai_category: str,
    ai_summary: str,
    status: str = "NEW",
    lead_id: str | None = None,
) -> int:
    """Persist a newly scored item to the database."""
    return await asyncio.to_thread(
        _save_item_sync,
        source_id,
        item_hash,
        title,
        url,
        raw_snippet,
        ai_score,
        ai_category,
        ai_summary,
        status,
        lead_id,
    )


def _update_item_status_sync(item_id: int, status: str) -> bool:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE items SET status = ? WHERE id = ?", (status, item_id))
        norm_status = "new"
        if status.upper() in ("SAVED", "BOOKMARKED"):
            norm_status = "bookmarked"
        elif status.upper() in ("ARCHIVED", "IGNORED"):
            norm_status = "ignored"
        cursor.execute(
            "UPDATE leads SET status = ? WHERE id = ? OR lead_id = ?",
            (norm_status, item_id, str(item_id)),
        )
        conn.commit()
        return cursor.rowcount > 0


async def update_item_status(item_id: int, status: str) -> bool:
    """Update item workflow status ('NEW', 'SAVED', 'ARCHIVED')."""
    return await asyncio.to_thread(_update_item_status_sync, item_id, status)


def _update_lead_user_status_sync(lead_id: str, new_status: str) -> None:
    norm_status = new_status.lower().strip()
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE leads
            SET status = ?
            WHERE lead_id = ? OR CAST(id AS TEXT) = ?
            """,
            (norm_status, str(lead_id), str(lead_id)),
        )

        item_status = "NEW"
        if norm_status == "bookmarked":
            item_status = "SAVED"
        elif norm_status == "ignored":
            item_status = "ARCHIVED"

        cursor.execute(
            """
            UPDATE items
            SET status = ?
            WHERE CAST(id AS TEXT) = ? OR item_hash = ?
            """,
            (item_status, str(lead_id), str(lead_id)),
        )

        if cursor.rowcount == 0:
            cursor.execute(
                "SELECT * FROM items WHERE CAST(id AS TEXT) = ? OR item_hash = ?",
                (str(lead_id), str(lead_id)),
            )
            item_row = cursor.fetchone()
            if item_row:
                cursor.execute("SELECT user_id FROM sources WHERE id = ?", (item_row["source_id"],))
                s_row = cursor.fetchone()
                uid = s_row["user_id"] if s_row else None
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO leads (
                        id, lead_id, user_id, source_id, item_hash, title, url, raw_snippet,
                        ai_score, ai_category, ai_summary, status, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_row["id"],
                        str(item_row["id"]),
                        uid,
                        item_row["source_id"],
                        item_row["item_hash"],
                        item_row["title"],
                        item_row["url"],
                        item_row["raw_snippet"],
                        item_row["ai_score"],
                        item_row["ai_category"],
                        item_row["ai_summary"],
                        norm_status,
                        item_row["created_at"],
                    ),
                )
        conn.commit()


async def update_lead_user_status(lead_id: str, new_status: str) -> None:
    """Update lead status to 'new', 'bookmarked', or 'ignored'."""
    await asyncio.to_thread(_update_lead_user_status_sync, lead_id, new_status)


def _get_lead_by_id_sync(lead_id: str) -> dict[str, Any] | None:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT l.*, COALESCE(s.name, 'Feed') as source_name
            FROM leads l
            LEFT JOIN sources s ON l.source_id = s.id
            WHERE l.lead_id = ? OR CAST(l.id AS TEXT) = ?
            """,
            (str(lead_id), str(lead_id)),
        )
        row = cursor.fetchone()
        if row:
            return dict(row)

        cursor.execute(
            """
            SELECT i.id, i.source_id, i.item_hash as lead_id, i.title, i.url, i.raw_snippet,
                   i.ai_score, i.ai_category, i.ai_summary,
                   CASE WHEN LOWER(i.status) = 'saved' THEN 'bookmarked'
                        WHEN LOWER(i.status) = 'archived' THEN 'ignored'
                        ELSE 'new' END as status,
                   i.created_at, s.name as source_name
            FROM items i
            LEFT JOIN sources s ON i.source_id = s.id
            WHERE CAST(i.id AS TEXT) = ? OR i.item_hash = ?
            """,
            (str(lead_id), str(lead_id)),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


async def get_lead_by_id(lead_id: str) -> dict[str, Any] | None:
    """Retrieve a lead by its lead_id or integer id."""
    return await asyncio.to_thread(_get_lead_by_id_sync, lead_id)


def _get_leads_for_export_sync(user_id: int, include_ignored: bool = False) -> list[dict[str, Any]]:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sources';")
        has_sources = cursor.fetchone() is not None

        if has_sources:
            query = """
                SELECT l.id, l.lead_id, l.user_id, l.source_id, l.title, l.url,
                       l.raw_snippet, l.ai_score, l.ai_category, l.ai_summary,
                       l.status, l.created_at, l.exported_at,
                       COALESCE(s.name, 'Feed') as source_name
                FROM leads l
                LEFT JOIN sources s ON l.source_id = s.id
                WHERE (l.user_id = ? OR s.user_id = ?)
            """
            params: list[Any] = [user_id, user_id]
        else:
            query = """
                SELECT l.id, l.lead_id, l.user_id, l.source_id, l.title, l.url,
                       l.raw_snippet, l.ai_score, l.ai_category, l.ai_summary,
                       l.status, l.created_at, l.exported_at,
                       'Feed' as source_name
                FROM leads l
                WHERE l.user_id = ?
            """
            params = [user_id]

        if not include_ignored:
            query += " AND l.status != 'ignored'"

        query += " ORDER BY l.created_at ASC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


async def get_leads_for_export(user_id: int, include_ignored: bool = False) -> list[dict[str, Any]]:
    """Query leads for export, strictly filtering WHERE status != 'ignored' when include_ignored is False. Order by created_at ASC."""
    return await asyncio.to_thread(_get_leads_for_export_sync, user_id, include_ignored)


def _update_leads_exported_at_sync(lead_ids: list[Any], timestamp: str) -> None:
    if not lead_ids:
        return
    placeholders = ",".join("?" for _ in lead_ids)
    str_ids = [str(x) for x in lead_ids]
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE leads SET exported_at = ? WHERE lead_id IN ({placeholders}) OR CAST(id AS TEXT) IN ({placeholders})",
            [timestamp] + str_ids + str_ids,
        )
        cursor.execute(
            f"UPDATE items SET exported_at = ? WHERE CAST(id AS TEXT) IN ({placeholders}) OR item_hash IN ({placeholders})",
            [timestamp] + str_ids + str_ids,
        )
        conn.commit()


async def update_leads_exported_at(lead_ids: list[Any], timestamp: str | None = None) -> None:
    """Update exported_at timestamp for a batch of lead IDs."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    await asyncio.to_thread(_update_leads_exported_at_sync, lead_ids, ts)


def _get_item_by_id_sync(item_id: int) -> dict[str, Any] | None:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, source_id, item_hash, title, url, raw_snippet,
                   ai_score, ai_category, ai_summary, status, created_at
            FROM items
            WHERE id = ?
            """,
            (item_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


async def get_item_by_id(item_id: int) -> dict[str, Any] | None:
    """Retrieve an item by its primary key ID."""
    return await asyncio.to_thread(_get_item_by_id_sync, item_id)


def _get_filtered_items_for_export_sync(
    user_id: int | None = None, min_score: int = 0
) -> list[dict[str, Any]]:
    with _get_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT i.id, i.created_at, s.name as source_name, i.ai_category,
                   i.ai_score, i.title, i.ai_summary, i.status, i.url
            FROM items i
            JOIN sources s ON i.source_id = s.id
            WHERE i.ai_score >= ?
        """
        params: list[Any] = [min_score]
        if user_id is not None:
            query += " AND s.user_id = ?"
            params.append(user_id)
        query += " ORDER BY i.id DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


async def get_filtered_items_for_export(
    user_id: int | None = None, min_score: int = 0
) -> list[dict[str, Any]]:
    """Retrieve items for CSV/Excel export joined with source metadata."""
    return await asyncio.to_thread(_get_filtered_items_for_export_sync, user_id, min_score)


def _get_radar_stats_sync(user_id: int) -> dict[str, int]:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM sources WHERE user_id = ? AND is_active = 1",
            (user_id,),
        )
        active_sources = cursor.fetchone()["count"]

        cursor.execute(
            """
            SELECT
                COUNT(i.id) as total_items,
                SUM(CASE WHEN i.ai_category = 'HOT_LEAD' THEN 1 ELSE 0 END) as hot_leads,
                SUM(CASE WHEN i.status = 'SAVED' THEN 1 ELSE 0 END) as saved_items
            FROM items i
            JOIN sources s ON i.source_id = s.id
            WHERE s.user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        total_items = row["total_items"] or 0
        hot_leads = row["hot_leads"] or 0
        saved_items = row["saved_items"] or 0

        return {
            "active_sources": active_sources,
            "total_items": total_items,
            "hot_leads": hot_leads,
            "saved_items": saved_items,
        }


async def get_radar_stats(user_id: int) -> dict[str, int]:
    """Retrieve aggregate monitoring metrics for a specific user."""
    return await asyncio.to_thread(_get_radar_stats_sync, user_id)


def _get_user_language_sync(user_id: int) -> str | None:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT language FROM user_settings WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row["language"]:
            return str(row["language"])
        cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row["language"]:
            return str(row["language"])
        cursor.execute("SELECT language FROM settings WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row["language"]:
            return str(row["language"])
        return None


async def get_user_language(user_id: int) -> str | None:
    """Retrieve stored language preference for a user."""
    return await asyncio.to_thread(_get_user_language_sync, user_id)


def _set_user_language_sync(user_id: int, lang: str | None) -> None:
    clean_lang = lang.strip().lower() if lang else None
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_settings (user_id, language) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET language = excluded.language
            """,
            (user_id, clean_lang),
        )
        cursor.execute(
            """
            INSERT INTO users (user_id, language) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET language = excluded.language
            """,
            (user_id, clean_lang),
        )
        cursor.execute(
            """
            INSERT INTO settings (user_id, language) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET language = excluded.language
            """,
            (user_id, clean_lang),
        )
        conn.commit()


async def set_user_language(user_id: int, lang: str | None) -> None:
    """Persist user language preference."""
    await asyncio.to_thread(_set_user_language_sync, user_id, lang)


def _has_user_record_sync(user_id: int) -> bool:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM user_settings WHERE user_id = ?", (user_id,))
        if cursor.fetchone() is not None:
            return True
        cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone() is not None:
            return True
        cursor.execute("SELECT 1 FROM settings WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None


async def has_user_record(user_id: int) -> bool:
    """Check if the user exists in database settings."""
    return await asyncio.to_thread(_has_user_record_sync, user_id)

