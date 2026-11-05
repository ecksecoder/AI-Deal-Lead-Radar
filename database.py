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
        conn.commit()
        return int(cursor.lastrowid)


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
    )


def _update_item_status_sync(item_id: int, status: str) -> bool:
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE items SET status = ? WHERE id = ?", (status, item_id))
        conn.commit()
        return cursor.rowcount > 0


async def update_item_status(item_id: int, status: str) -> bool:
    """Update item workflow status ('NEW', 'SAVED', 'ARCHIVED')."""
    return await asyncio.to_thread(_update_item_status_sync, item_id, status)


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
