"""Excel-compatible CSV reporting engine for AI Deal & Lead Radar."""

import asyncio
import csv
import logging
import os
import time
from typing import Any
from config import EXPORT_DIR
from database import get_filtered_items_for_export

logger = logging.getLogger("radar.exporter")

CSV_COLUMNS: list[str] = [
    "ID",
    "Date",
    "Source",
    "Category",
    "AI Score",
    "Title",
    "Summary",
    "Status",
    "URL",
]


def _write_csv_sync(items: list[dict[str, Any]], output_path: str) -> str:
    """Synchronously write items into an Excel-friendly CSV with UTF-8 BOM.

    Args:
        items: List of dictionary records from database.
        output_path: Target filesystem path.

    Returns:
        The written output path.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # utf-8-sig automatically prepends the UTF-8 Byte Order Mark (BOM: \xef\xbb\xbf)
    with open(output_path, mode="w", encoding="utf-8-sig", newline="") as csvfile:
        writer = csv.writer(
            csvfile,
            delimiter=";",
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\r\n",
        )
        writer.writerow(CSV_COLUMNS)

        for item in items:
            writer.writerow(
                [
                    item.get("id", ""),
                    item.get("created_at", ""),
                    item.get("source_name", "Демо-поток"),
                    item.get("ai_category", "STANDARD"),
                    item.get("ai_score", 0),
                    item.get("title", ""),
                    item.get("ai_summary", ""),
                    item.get("status", "NEW"),
                    item.get("url", ""),
                ]
            )

    logger.info("Successfully generated CSV export with %d rows: %s", len(items), output_path)
    return output_path


async def export_items_to_csv(user_id: int | None = None, min_score: int = 0) -> str:
    """Generate an Excel-compatible CSV file for all filtered items.

    Args:
        user_id: Optional Telegram user ID to restrict records.
        min_score: Minimum AI score threshold.

    Returns:
        Absolute filesystem path to the generated CSV file.
    """
    items = await get_filtered_items_for_export(user_id=user_id, min_score=min_score)

    os.makedirs(EXPORT_DIR, exist_ok=True)
    timestamp = int(time.time())
    user_suffix = str(user_id) if user_id is not None else "all"
    filename = f"radar_export_{user_suffix}_{timestamp}.csv"
    output_path = os.path.join(EXPORT_DIR, filename)

    return await asyncio.to_thread(_write_csv_sync, items, output_path)


def cleanup_export(file_path: str) -> None:
    """Safely delete a temporary exported file.

    Args:
        file_path: Path to the exported CSV file.
    """
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.info("Cleaned up temporary export file: %s", file_path)
    except OSError as exc:
        logger.warning("Failed to clean up export file %s: %s", file_path, exc)
