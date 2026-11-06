"""Excel-compatible CSV and XLSX reporting engine for AI Deal & Lead Radar."""

import asyncio
import csv
from datetime import datetime
import logging
import os
import time
from typing import Any
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from config import EXPORT_DIR
from database import get_filtered_items_for_export
from locales import get_text

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


def _write_csv_sync(
    items: list[dict[str, Any]], output_path: str, headers: list[str] | None = None
) -> str:
    """Synchronously write items into an Excel-friendly CSV with UTF-8 BOM.

    Args:
        items: List of dictionary records from database.
        output_path: Target filesystem path.
        headers: Localized list of column headers.

    Returns:
        The written output path.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    cols = headers if headers else CSV_COLUMNS

    # utf-8-sig automatically prepends the UTF-8 Byte Order Mark (BOM: \xef\xbb\xbf)
    with open(output_path, mode="w", encoding="utf-8-sig", newline="") as csvfile:
        writer = csv.writer(
            csvfile,
            delimiter=";",
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\r\n",
        )
        writer.writerow(cols)

        for item in items:
            writer.writerow(
                [
                    item.get("id", ""),
                    item.get("created_at", ""),
                    item.get("source_name", "Feed"),
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


def _write_xlsx_sync(
    leads: list[dict[str, Any]],
    output_path: str,
    headers: list[str] | None = None,
    lang: str = "en",
    now_datetime: datetime | None = None,
) -> tuple[str, list[Any]]:
    """Synchronously write leads into an Excel file with an accent-styled separator row."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leads"

    cols = headers if headers else CSV_COLUMNS

    # Header styling
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.append(cols)
    for col_idx in range(1, len(cols) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
    ws.row_dimensions[1].height = 28

    previously_exported = [l for l in leads if l.get("exported_at") is not None]
    new_records = [l for l in leads if l.get("exported_at") is None]

    if not new_records and previously_exported:
        new_records = list(leads)
        previously_exported = []

    for item in previously_exported:
        ws.append(
            [
                item.get("id") or item.get("lead_id", ""),
                item.get("created_at", ""),
                item.get("source_name", "Feed"),
                item.get("ai_category", "STANDARD"),
                item.get("ai_score", 0),
                item.get("title", ""),
                item.get("ai_summary", ""),
                item.get("status", "new"),
                item.get("url", ""),
            ]
        )

    # Accent-styled separator row: light gray fill #EFEFEF, bold italic centered text
    dt = now_datetime or datetime.now()
    dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    batch_count = len(new_records)
    sep_text = get_text("export_batch_separator", lang, datetime=dt_str, count=batch_count)

    sep_fill = PatternFill(start_color="EFEFEF", end_color="EFEFEF", fill_type="solid")
    sep_font = Font(name="Calibri", size=10, bold=True, italic=True, color="333333")
    sep_align = Alignment(horizontal="center", vertical="center")

    sep_row_idx = ws.max_row + 1
    ws.append([sep_text] + [""] * (len(cols) - 1))
    ws.merge_cells(start_row=sep_row_idx, start_column=1, end_row=sep_row_idx, end_column=len(cols))

    for col_idx in range(1, len(cols) + 1):
        cell = ws.cell(row=sep_row_idx, column=col_idx)
        cell.fill = sep_fill
        cell.font = sep_font
        cell.alignment = sep_align
    ws.row_dimensions[sep_row_idx].height = 24

    for item in new_records:
        ws.append(
            [
                item.get("id") or item.get("lead_id", ""),
                item.get("created_at", ""),
                item.get("source_name", "Feed"),
                item.get("ai_category", "STANDARD"),
                item.get("ai_score", 0),
                item.get("title", ""),
                item.get("ai_summary", ""),
                item.get("status", "new"),
                item.get("url", ""),
            ]
        )

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row == sep_row_idx:
                continue
            val = str(cell.value or "")
            if len(val) > max_len:
                max_len = len(val)
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 60)

    wb.save(output_path)
    logger.info("Successfully generated XLSX export with separator at row %d: %s", sep_row_idx, output_path)

    exported_ids = [
        l.get("id") or l.get("lead_id")
        for l in new_records
        if (l.get("id") or l.get("lead_id")) is not None
    ]
    return output_path, exported_ids


async def export_leads_to_xlsx(
    leads: list[dict[str, Any]],
    user_id: int | None = None,
    lang: str = "en",
    headers: list[str] | None = None,
    now_datetime: datetime | None = None,
) -> tuple[str, list[Any]]:
    """Generate an Excel (.xlsx) file with an accent-styled session separator row.

    Args:
        leads: Filtered lead records to export.
        user_id: Target user ID.
        lang: Target interface locale.
        headers: Localized column headers.
        now_datetime: Optional timestamp override.

    Returns:
        Tuple of (absolute file path, list of exported lead IDs).
    """
    os.makedirs(EXPORT_DIR, exist_ok=True)
    dt = now_datetime or datetime.now()
    timestamp = int(dt.timestamp())
    user_suffix = str(user_id) if user_id is not None else "all"
    filename = f"radar_export_{user_suffix}_{timestamp}.xlsx"
    output_path = os.path.join(EXPORT_DIR, filename)

    return await asyncio.to_thread(
        _write_xlsx_sync,
        leads,
        output_path,
        headers,
        lang,
        dt,
    )


async def export_items_to_csv(
    user_id: int | None = None, min_score: int = 0, headers: list[str] | None = None
) -> str:
    """Generate an Excel-compatible CSV file for all filtered items.

    Args:
        user_id: Optional Telegram user ID to restrict records.
        min_score: Minimum AI score threshold.
        headers: Optional localized column headers.

    Returns:
        Absolute filesystem path to the generated CSV file.
    """
    items = await get_filtered_items_for_export(user_id=user_id, min_score=min_score)

    os.makedirs(EXPORT_DIR, exist_ok=True)
    timestamp = int(time.time())
    user_suffix = str(user_id) if user_id is not None else "all"
    filename = f"radar_export_{user_suffix}_{timestamp}.csv"
    output_path = os.path.join(EXPORT_DIR, filename)

    return await asyncio.to_thread(_write_csv_sync, items, output_path, headers)


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
