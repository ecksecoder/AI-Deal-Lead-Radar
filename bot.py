"""Main Telegram Bot and background monitoring worker for AI Deal & Lead Radar."""

import asyncio
from datetime import datetime
import html
import logging
from typing import Any
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from ai_scorer import score_item
from config import (
    ADMIN_IDS,
    BOT_TOKEN,
    MIN_ALERT_SCORE,
    POLL_INTERVAL_SECONDS,
    is_safe_url,
    validate_config,
)
from database import (
    add_source,
    delete_source,
    get_active_sources,
    get_lead_by_id,
    get_leads_for_export,
    get_radar_stats,
    get_source_by_id,
    get_user_language,
    get_user_sources,
    has_user_record,
    init_db,
    is_item_seen,
    save_item,
    set_user_language,
    toggle_source,
    update_item_status,
    update_lead_user_status,
    update_leads_exported_at,
    update_source_checked,
)
from exporter import cleanup_export, export_items_to_csv, export_leads_to_xlsx
from locales import (
    detect_locale,
    get_button_variants,
    get_export_headers,
    get_language_inline_kb,
    get_text,
)
from scraper import generate_demo_items, scrape_source

logger = logging.getLogger("radar.bot")

router = Router()


class AddSourceState(StatesGroup):
    """FSM states for registering a new monitoring source."""

    waiting_for_type = State()
    waiting_for_url = State()
    waiting_for_name = State()
    waiting_for_keywords = State()


def is_authorized(user_id: int) -> bool:
    """Check if the Telegram user ID is authorized under RBAC policy."""
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS


async def resolve_user_locale(user_id: int, telegram_lang: str | None) -> tuple[str, bool]:
    """Resolve active language and auto detection flag.

    Checks DB preference first; if absent or set to 'auto', falls back to Telegram client locale.
    """
    saved_lang = await get_user_language(user_id)
    if saved_lang and saved_lang in ("en", "uk", "ru"):
        return saved_lang, False
    return detect_locale(telegram_lang), True


async def resolve_user_lang(user_id: int, telegram_lang: str | None) -> str:
    """Backward-compatible helper returning active locale string."""
    locale, _ = await resolve_user_locale(user_id, telegram_lang)
    return locale


def get_main_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    """Build the persistent bottom control panel."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=get_text("btn_sources", lang)),
                KeyboardButton(text=get_text("btn_add_source", lang)),
            ],
            [
                KeyboardButton(text=get_text("btn_demo", lang)),
                KeyboardButton(text=get_text("btn_export", lang)),
            ],
            [
                KeyboardButton(text=get_text("btn_lang", lang)),
            ],
        ],
        resize_keyboard=True,
    )


def build_lead_card_kb(lead_id: str, status: str, url: str, lang: str = "en") -> InlineKeyboardMarkup:
    """Helper to build high-contrast interactive triage state toggling keyboard.

    Row 1: Open Link button.
    Row 2: Bookmark button (⭐ idle / ✅ active) and Ignore button (🗑️ idle / ❌ active).
    """
    clean_status = (status or "new").lower().strip()
    clean_lang = (lang or "en").lower().strip()

    bookmark_text = (
        get_text("btn_bookmark_active", clean_lang)
        if clean_status == "bookmarked"
        else get_text("btn_bookmark_idle", clean_lang)
    )
    ignore_text = (
        get_text("btn_ignore_active", clean_lang)
        if clean_status == "ignored"
        else get_text("btn_ignore_idle", clean_lang)
    )

    clean_url = (url or "").strip()
    if clean_url and not clean_url.startswith(("http://", "https://", "tg://")):
        clean_url = f"https://{clean_url}"

    open_url = clean_url if clean_url.startswith(("http://", "https://", "tg://")) else "https://freelance-radar.internal"

    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=get_text("card_btn_open", clean_lang), url=open_url),
        ],
        [
            InlineKeyboardButton(text=bookmark_text, callback_data=f"action_bookmark:{lead_id}"),
            InlineKeyboardButton(text=ignore_text, callback_data=f"action_ignore:{lead_id}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_alert_card(
    title: str,
    source_name: str,
    category: str,
    score: int,
    summary: str,
    url: str,
    item_id: int | str,
    status: str = "new",
    lang: str = "en",
) -> tuple[str, InlineKeyboardMarkup]:
    """Render an HTML alert card with interactive Micro-CRM inline buttons."""
    header_alert = get_text("lead_alert_header", lang)
    badge_key = f"badge_{category.lower()}"
    badge_header = get_text(badge_key, lang, score=score)
    if badge_header == badge_key:
        badge_header = get_text("badge_lead", lang, category=category, score=score)

    status_key = f"status_{status.lower()}"
    status_localized = get_text(status_key, lang)
    if status_localized == status_key:
        status_localized = status

    source_label = get_text("alert_source", lang, source_name=html.escape(source_name))
    summary_header = get_text("alert_ai_summary", lang)
    status_label = get_text("alert_status", lang, status=status_localized)

    text = (
        f"{header_alert}\n\n"
        f"{badge_header}\n\n"
        f"💼 <b>{html.escape(title)}</b>\n"
        f"{source_label}\n\n"
        f"{summary_header}\n"
        f"{html.escape(summary)}\n\n"
        f"{status_label}"
    )

    kb = build_lead_card_kb(lead_id=str(item_id), status=status.lower(), url=url, lang=lang)
    return text, kb


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start command with onboarding gate and executive dashboard."""
    await state.clear()
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, is_auto = await resolve_user_locale(user_id, telegram_lang)

    if not is_authorized(user_id):
        logger.warning("Unauthorized access attempt by user %d", user_id)
        await message.answer(get_text("unauthorized", lang, user_id=user_id))
        return

    # Onboarding gate: if user has no DB record, send trilingual selection banner
    if not await has_user_record(user_id):
        banner_text = get_text("onboarding_banner", lang)
        inline_kb = get_language_inline_kb(active_lang=lang, is_auto=is_auto, prefix="lang_set")
        await message.answer(banner_text, reply_markup=inline_kb)
        return

    stats = await get_radar_stats(user_id)
    text = get_text(
        "start_dashboard",
        lang,
        active_sources=stats["active_sources"],
        total_items=stats["total_items"],
        hot_leads=stats["hot_leads"],
        saved_items=stats["saved_items"],
    )
    await message.answer(text, reply_markup=get_main_keyboard(lang))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Display help information and command directory."""
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)
    await message.answer(get_text("help_text", lang))


@router.message(Command("lang"))
@router.message(Command("language"))
@router.message(F.text.in_(get_button_variants("btn_lang")))
async def cmd_language(message: Message) -> None:
    """Display inline language selection keyboard with trilingual header."""
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, is_auto = await resolve_user_locale(user_id, telegram_lang)
    banner_text = get_text("choose_language", lang)
    inline_kb = get_language_inline_kb(active_lang=lang, is_auto=is_auto, prefix="lang_set")
    await message.answer(banner_text, reply_markup=inline_kb)


@router.callback_query(F.data.startswith("lang_set:"))
async def cb_set_language(callback: CallbackQuery) -> None:
    """Process language selection: update DB, refresh markup in-place, and update ReplyKeyboardMarkup immediately."""
    if not callback.data:
        return
    chosen = callback.data.split(":")[1]
    user_id = callback.from_user.id if callback.from_user else 0
    telegram_lang = callback.from_user.language_code if callback.from_user else None

    if chosen == "auto":
        await set_user_language(user_id, "auto")
        new_lang = detect_locale(telegram_lang)
        is_auto = True
        toast_text = get_text("language_changed_auto", new_lang)
    else:
        new_lang = chosen
        is_auto = False
        await set_user_language(user_id, new_lang)
        toast_text = get_text("language_changed", new_lang)

    clean_toast = toast_text.replace("<b>", "").replace("</b>", "")
    await callback.answer(clean_toast)

    # Refresh inline markup in-place (updating Auto label and checkmark to the new language)
    new_kb = get_language_inline_kb(active_lang=new_lang, is_auto=is_auto, prefix="lang_set")
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                get_text("choose_language", new_lang),
                reply_markup=new_kb,
            )
        except Exception:
            try:
                await callback.message.edit_reply_markup(reply_markup=new_kb)
            except Exception:
                pass

        # Update ReplyKeyboardMarkup immediately
        await callback.message.answer(
            get_text("menu_refreshed", new_lang),
            reply_markup=get_main_keyboard(new_lang),
        )


@router.message(Command("demo"))
@router.message(F.text.in_(get_button_variants("btn_demo")))
async def handle_demo_run(message: Message) -> None:
    """Simulate live ingestion of 3 realistic B2B leads with instant scoring and alert cards."""
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    if not is_authorized(user_id):
        await message.answer(get_text("access_restricted", lang))
        return

    status_msg = await message.answer(get_text("demo_starting", lang))

    feed_name = get_text("demo_feed_name", lang)
    # Ensure demo source exists for this user
    sources = await get_user_sources(user_id)
    demo_source = next((s for s in sources if s["source_type"] == "demo"), None)
    if not demo_source:
        demo_id = await add_source(
            user_id=user_id,
            name=feed_name,
            url="internal://demo-feed",
            source_type="demo",
            keywords="python, bot, ai, automation, scraping, llm",
        )
    else:
        demo_id = demo_source["id"]

    demo_items = generate_demo_items("python, bot, ai, automation, scraping, llm", lang=lang)
    cards_sent = 0

    for item in demo_items:
        # Check if already seen
        seen = await is_item_seen(item["item_hash"])
        item_lead_id = item.get("lead_id") or item.get("id")
        if not seen:
            scored = await score_item(
                title=item["title"],
                snippet=item["raw_snippet"],
                keywords="python, bot, ai, automation, scraping, llm",
                lang=lang,
            )
            item_id = await save_item(
                source_id=demo_id,
                item_hash=item["item_hash"],
                title=item["title"],
                url=item["url"],
                raw_snippet=item["raw_snippet"],
                ai_score=scored["score"],
                ai_category=scored["category"],
                ai_summary=scored["summary"],
                status="new",
                lead_id=item_lead_id,
            )
            card_lead_id = item_lead_id or str(item_id)
            card_text, card_markup = format_alert_card(
                title=item["title"],
                source_name=feed_name,
                category=scored["category"],
                score=scored["score"],
                summary=scored["summary"],
                url=item["url"],
                item_id=card_lead_id,
                status="new",
                lang=lang,
            )
        else:
            scored = await score_item(
                title=item["title"],
                snippet=item["raw_snippet"],
                keywords="python, bot, ai, automation, scraping, llm",
                lang=lang,
            )
            seen_lead = await get_lead_by_id(item_lead_id) if item_lead_id else None
            card_lead_id = item_lead_id or (str(seen_lead["id"]) if seen_lead else "1")
            card_status = (seen_lead.get("status") if seen_lead else "new") or "new"
            card_text, card_markup = format_alert_card(
                title=item["title"],
                source_name=feed_name,
                category=scored["category"],
                score=scored["score"],
                summary=scored["summary"],
                url=item["url"],
                item_id=card_lead_id,
                status=card_status,
                lang=lang,
            )

        await message.answer(card_text, reply_markup=card_markup)
        cards_sent += 1
        await asyncio.sleep(0.3)

    await status_msg.edit_text(get_text("demo_completed", lang, cards_sent=cards_sent))


@router.message(Command("sources"))
@router.message(F.text.in_(get_button_variants("btn_sources")))
async def handle_list_sources(message: Message) -> None:
    """Display user's configured monitoring sources with inline controls."""
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    if not is_authorized(user_id):
        await message.answer(get_text("access_restricted", lang))
        return

    sources = await get_user_sources(user_id)
    if not sources:
        await message.answer(
            get_text("sources_empty", lang),
            reply_markup=get_main_keyboard(lang),
        )
        return

    await message.answer(get_text("sources_header", lang, count=len(sources)))

    for src in sources:
        status_text = (
            get_text("source_status_active", lang)
            if src["is_active"]
            else get_text("source_status_paused", lang)
        )
        toggle_label = (
            get_text("source_btn_pause", lang)
            if src["is_active"]
            else get_text("source_btn_start", lang)
        )
        last_check = src["last_checked_at"] or get_text("source_not_checked", lang)
        if "T" in last_check:
            last_check = last_check.split("T")[0] + " " + last_check.split("T")[1][:5]

        info_text = get_text(
            "source_card_info",
            lang,
            name=html.escape(src["name"]),
            status=status_text,
            type=src["source_type"].upper(),
            url=html.escape(src["url"]),
            keywords=html.escape(src["keywords"] or get_text("source_all_keywords", lang)),
            last_check=last_check,
        )

        buttons = [
            [
                InlineKeyboardButton(
                    text=toggle_label,
                    callback_data=f"src:toggle:{src['id']}",
                ),
                InlineKeyboardButton(
                    text=get_text("source_btn_check", lang),
                    callback_data=f"src:check:{src['id']}",
                ),
                InlineKeyboardButton(
                    text=get_text("source_btn_delete", lang),
                    callback_data=f"src:del:{src['id']}",
                ),
            ]
        ]
        await message.answer(info_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("src:toggle:"))
async def cb_toggle_source(callback: CallbackQuery) -> None:
    """Toggle activation state of a monitoring source."""
    if not callback.data:
        return
    user_id = callback.from_user.id if callback.from_user else 0
    telegram_lang = callback.from_user.language_code if callback.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    source_id = int(callback.data.split(":")[2])
    new_state = await toggle_source(source_id)
    state_desc = (
        get_text("source_toggled_active", lang)
        if new_state
        else get_text("source_toggled_paused", lang)
    )
    await callback.answer(state_desc)

    src = await get_source_by_id(source_id)
    if src and callback.message and isinstance(callback.message, Message):
        status_text = (
            get_text("source_status_active", lang)
            if new_state
            else get_text("source_status_paused", lang)
        )
        toggle_label = (
            get_text("source_btn_pause", lang)
            if new_state
            else get_text("source_btn_start", lang)
        )
        last_check = src["last_checked_at"] or get_text("source_not_checked", lang)
        if "T" in last_check:
            last_check = last_check.split("T")[0] + " " + last_check.split("T")[1][:5]

        info_text = get_text(
            "source_card_info",
            lang,
            name=html.escape(src["name"]),
            status=status_text,
            type=src["source_type"].upper(),
            url=html.escape(src["url"]),
            keywords=html.escape(src["keywords"] or get_text("source_all_keywords", lang)),
            last_check=last_check,
        )
        buttons = [
            [
                InlineKeyboardButton(
                    text=toggle_label,
                    callback_data=f"src:toggle:{src['id']}",
                ),
                InlineKeyboardButton(
                    text=get_text("source_btn_check", lang),
                    callback_data=f"src:check:{src['id']}",
                ),
                InlineKeyboardButton(
                    text=get_text("source_btn_delete", lang),
                    callback_data=f"src:del:{src['id']}",
                ),
            ]
        ]
        await callback.message.edit_text(
            info_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )


@router.callback_query(F.data.startswith("src:del:"))
async def cb_delete_source(callback: CallbackQuery) -> None:
    """Delete a monitoring source."""
    if not callback.data:
        return
    user_id = callback.from_user.id if callback.from_user else 0
    telegram_lang = callback.from_user.language_code if callback.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    source_id = int(callback.data.split(":")[2])
    await delete_source(source_id)
    await callback.answer(get_text("source_deleted_toast", lang))
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(get_text("source_deleted_msg", lang))


@router.callback_query(F.data.startswith("src:check:"))
async def cb_check_source(callback: CallbackQuery) -> None:
    """Trigger an immediate scraping cycle for a single source."""
    if not callback.data:
        return
    user_id = callback.from_user.id if callback.from_user else 0
    telegram_lang = callback.from_user.language_code if callback.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    source_id = int(callback.data.split(":")[2])
    src = await get_source_by_id(source_id)
    if not src:
        await callback.answer(get_text("source_not_found", lang))
        return

    await callback.answer(get_text("source_check_started", lang))
    items = await scrape_source(src, lang=lang)
    new_count = 0
    alert_count = 0

    for item in items:
        seen = await is_item_seen(item["item_hash"])
        if seen:
            continue
        new_count += 1
        scored = await score_item(
            title=item["title"],
            snippet=item["raw_snippet"],
            keywords=src["keywords"],
            lang=lang,
        )
        item_id = await save_item(
            source_id=src["id"],
            item_hash=item["item_hash"],
            title=item["title"],
            url=item["url"],
            raw_snippet=item["raw_snippet"],
            ai_score=scored["score"],
            ai_category=scored["category"],
            ai_summary=scored["summary"],
            status="NEW",
        )
        if scored["score"] >= MIN_ALERT_SCORE and callback.message:
            alert_count += 1
            card_text, card_markup = format_alert_card(
                title=item["title"],
                source_name=src["name"],
                category=scored["category"],
                score=scored["score"],
                summary=scored["summary"],
                url=item["url"],
                item_id=item_id,
                status="NEW",
                lang=lang,
            )
            await callback.message.answer(card_text, reply_markup=card_markup)

    await update_source_checked(source_id)
    if callback.message:
        await callback.message.answer(
            get_text(
                "source_check_done",
                lang,
                name=html.escape(src["name"]),
                new_count=new_count,
                alert_count=alert_count,
            )
        )


@router.callback_query(F.data.startswith("action_bookmark:"))
async def cb_action_bookmark(callback: CallbackQuery) -> None:
    """Toggle status between 'bookmarked' and 'new' in DB, re-render keyboard in-place, and answer callback."""
    if not callback.data:
        return
    lead_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id if callback.from_user else 0
    telegram_lang = callback.from_user.language_code if callback.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    lead = await get_lead_by_id(lead_id)
    current_status = (lead.get("status") or "new").lower() if lead else "new"

    new_status = "new" if current_status == "bookmarked" else "bookmarked"
    await update_lead_user_status(lead_id, new_status)

    url = lead.get("url", "") if lead else ""
    if not url and callback.message and callback.message.reply_markup and callback.message.reply_markup.inline_keyboard:
        first_row = callback.message.reply_markup.inline_keyboard[0]
        if first_row and first_row[0].url:
            url = first_row[0].url

    new_kb = build_lead_card_kb(lead_id=lead_id, status=new_status, url=url, lang=lang)

    if callback.message and hasattr(callback.message, "edit_reply_markup"):
        try:
            await callback.message.edit_reply_markup(reply_markup=new_kb)
        except Exception as exc:
            logger.debug("Failed to edit reply markup for bookmark action: %s", exc)

    await callback.answer()


@router.callback_query(F.data.startswith("action_ignore:"))
async def cb_action_ignore(callback: CallbackQuery) -> None:
    """Toggle status between 'ignored' and 'new' in DB, update keyboard in-place to display active '❌ Ignored' (or revert), and answer callback."""
    if not callback.data:
        return
    lead_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id if callback.from_user else 0
    telegram_lang = callback.from_user.language_code if callback.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    lead = await get_lead_by_id(lead_id)
    current_status = (lead.get("status") or "new").lower() if lead else "new"

    new_status = "new" if current_status == "ignored" else "ignored"
    await update_lead_user_status(lead_id, new_status)

    url = lead.get("url", "") if lead else ""
    if not url and callback.message and callback.message.reply_markup and callback.message.reply_markup.inline_keyboard:
        first_row = callback.message.reply_markup.inline_keyboard[0]
        if first_row and first_row[0].url:
            url = first_row[0].url

    new_kb = build_lead_card_kb(lead_id=lead_id, status=new_status, url=url, lang=lang)

    if callback.message and hasattr(callback.message, "edit_reply_markup"):
        try:
            await callback.message.edit_reply_markup(reply_markup=new_kb)
        except Exception as exc:
            logger.debug("Failed to edit reply markup for ignore action: %s", exc)

    await callback.answer()


@router.callback_query(F.data.startswith("crm:"))
async def cb_crm_action(callback: CallbackQuery) -> None:
    """Handle legacy Micro-CRM lead actions (crm:save, crm:arch)."""
    if not callback.data:
        return
    user_id = callback.from_user.id if callback.from_user else 0
    telegram_lang = callback.from_user.language_code if callback.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    parts = callback.data.split(":")
    action = parts[1]
    item_id = parts[2]

    new_status = "bookmarked" if action == "save" else "ignored"
    await update_lead_user_status(item_id, new_status)

    lead = await get_lead_by_id(item_id)
    url = lead.get("url", "") if lead else ""
    if not url and callback.message and callback.message.reply_markup and callback.message.reply_markup.inline_keyboard:
        first_row = callback.message.reply_markup.inline_keyboard[0]
        if first_row and first_row[0].url:
            url = first_row[0].url

    new_kb = build_lead_card_kb(lead_id=str(item_id), status=new_status, url=url, lang=lang)

    if callback.message and hasattr(callback.message, "edit_reply_markup"):
        try:
            await callback.message.edit_reply_markup(reply_markup=new_kb)
        except Exception:
            pass

    toast = get_text("crm_saved_toast" if action == "save" else "crm_archived_toast", lang)
    await callback.answer(toast)


@router.message(Command("add"))
@router.message(F.text.in_(get_button_variants("btn_add_source")))
async def handle_add_source_start(message: Message, state: FSMContext) -> None:
    """Begin FSM wizard for adding a new monitoring source."""
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    if not is_authorized(user_id):
        await message.answer(get_text("access_restricted", lang))
        return

    buttons = [
        [
            InlineKeyboardButton(text=get_text("add_type_rss", lang), callback_data="add_type:rss"),
            InlineKeyboardButton(text=get_text("add_type_html", lang), callback_data="add_type:html"),
        ],
        [
            InlineKeyboardButton(text=get_text("add_type_demo", lang), callback_data="add_type:demo"),
        ],
    ]
    await state.set_state(AddSourceState.waiting_for_type)
    await message.answer(
        get_text("add_step_1", lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("add_type:"), AddSourceState.waiting_for_type)
async def cb_add_source_type(callback: CallbackQuery, state: FSMContext) -> None:
    """Process selected source type and transition to URL input."""
    if not callback.data:
        return
    user_id = callback.from_user.id if callback.from_user else 0
    telegram_lang = callback.from_user.language_code if callback.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    stype = callback.data.split(":")[1]
    await state.update_data(source_type=stype)

    if stype == "demo":
        await state.update_data(url="internal://demo-feed")
        await state.set_state(AddSourceState.waiting_for_name)
        await callback.answer()
        if callback.message:
            await callback.message.answer(get_text("add_step_demo_name", lang))
    else:
        await state.set_state(AddSourceState.waiting_for_url)
        await callback.answer()
        if callback.message:
            await callback.message.answer(get_text("add_step_url", lang))


@router.message(AddSourceState.waiting_for_url)
async def handle_add_source_url(message: Message, state: FSMContext) -> None:
    """Validate submitted URL against SSRF and advance to source name input."""
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    url = (message.text or "").strip()
    safe, reason = is_safe_url(url)
    if not safe:
        await message.answer(get_text("add_invalid_url", lang, reason=reason))
        return

    await state.update_data(url=url)
    await state.set_state(AddSourceState.waiting_for_name)
    await message.answer(get_text("add_step_name", lang))


@router.message(AddSourceState.waiting_for_name)
async def handle_add_source_name(message: Message, state: FSMContext) -> None:
    """Store source name and prompt for evaluation criteria."""
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    name = (message.text or "").strip()
    if not name:
        await message.answer(get_text("add_empty_name", lang))
        return

    await state.update_data(name=name)
    await state.set_state(AddSourceState.waiting_for_keywords)
    await message.answer(get_text("add_step_keywords", lang))


@router.message(AddSourceState.waiting_for_keywords)
async def handle_add_source_keywords(message: Message, state: FSMContext) -> None:
    """Save completed source configuration to database."""
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    raw_kw = (message.text or "").strip()
    keywords = "" if raw_kw == "-" else raw_kw

    data = await state.get_data()
    await state.clear()

    source_id = await add_source(
        user_id=user_id,
        name=data["name"],
        url=data["url"],
        source_type=data["source_type"],
        keywords=keywords,
    )

    await message.answer(
        get_text(
            "add_success",
            lang,
            source_id=source_id,
            name=html.escape(data["name"]),
            type=data["source_type"].upper(),
            keywords=html.escape(keywords or get_text("source_all_keywords", lang)),
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=get_text("btn_check_now", lang),
                        callback_data=f"src:check:{source_id}",
                    )
                ]
            ]
        ),
    )


@router.message(Command("export"))
@router.message(F.text.in_(get_button_variants("btn_export")))
async def handle_export_report(message: Message) -> None:
    """Generate and dispatch an Excel report with batch separators and excluded ignored leads."""
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    user_lang = await get_user_language(user_id) or lang or "en"
    if user_lang not in ("en", "uk", "ru"):
        user_lang = "en"

    if not is_authorized(user_id):
        await message.answer(get_text("access_restricted", user_lang))
        return

    status_msg = await message.answer(get_text("export_preparing", user_lang))

    export_path: str = ""
    try:
        leads = await get_leads_for_export(user_id=user_id, include_ignored=False)
        headers = get_export_headers(user_lang)
        now_dt = datetime.now()
        now_str = now_dt.strftime("%Y%m%d_%H%M%S")

        export_path, exported_ids = await export_leads_to_xlsx(
            leads=leads,
            user_id=user_id,
            lang=user_lang,
            headers=headers,
            now_datetime=now_dt,
        )

        if exported_ids:
            await update_leads_exported_at(exported_ids, now_dt.isoformat())

        input_file = FSInputFile(export_path, filename=f"radar_leads_{now_str}.xlsx")
        await message.answer_document(
            input_file,
            caption=get_text("export_caption", user_lang),
        )
        await status_msg.delete()
    except Exception as exc:
        logger.error("Failed to generate or send export: %s", exc)
        await status_msg.edit_text(get_text("export_error", user_lang, error=exc))
    finally:
        if export_path:
            cleanup_export(export_path)


async def monitoring_worker(bot: Bot) -> None:
    """Background async worker periodically scraping active sources and alerting users."""
    logger.info("Background monitoring worker started. Polling every %ds.", POLL_INTERVAL_SECONDS)
    while True:
        try:
            active_sources = await get_active_sources()
            logger.info("Monitoring cycle starting for %d active sources.", len(active_sources))

            for src in active_sources:
                try:
                    subscriber_id = src["user_id"]
                    user_lang = await get_user_language(subscriber_id) or "en"
                    if user_lang not in ("en", "uk", "ru"):
                        user_lang = "en"

                    items = await scrape_source(src, lang=user_lang)
                    for item in items:
                        seen = await is_item_seen(item["item_hash"])
                        if seen:
                            continue

                        scored = await score_item(
                            title=item["title"],
                            snippet=item["raw_snippet"],
                            keywords=src.get("keywords", ""),
                            lang=user_lang,
                        )
                        item_id = await save_item(
                            source_id=src["id"],
                            item_hash=item["item_hash"],
                            title=item["title"],
                            url=item["url"],
                            raw_snippet=item["raw_snippet"],
                            ai_score=scored["score"],
                            ai_category=scored["category"],
                            ai_summary=scored["summary"],
                            status="NEW",
                        )

                        if scored["score"] >= MIN_ALERT_SCORE:
                            card_text, card_markup = format_alert_card(
                                title=item["title"],
                                source_name=src["name"],
                                category=scored["category"],
                                score=scored["score"],
                                summary=scored["summary"],
                                url=item["url"],
                                item_id=item_id,
                                status="NEW",
                                lang=user_lang,
                            )
                            try:
                                await bot.send_message(
                                    chat_id=subscriber_id,
                                    text=card_text,
                                    reply_markup=card_markup,
                                )
                            except Exception as send_exc:
                                logger.warning(
                                    "Failed to send alert to user %d: %s",
                                    subscriber_id,
                                    send_exc,
                                )

                    await update_source_checked(src["id"])
                except Exception as src_exc:
                    logger.error(
                        "Error processing source %s (%d): %s",
                        src.get("name"),
                        src.get("id"),
                        src_exc,
                    )

            logger.info("Monitoring cycle completed. Sleeping for %ds.", POLL_INTERVAL_SECONDS)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        except asyncio.CancelledError:
            logger.info("Monitoring worker received cancellation signal. Shutting down gracefully.")
            break
        except Exception as cycle_exc:
            logger.error("Unhandled error in monitoring worker cycle: %s", cycle_exc)
            await asyncio.sleep(15)


async def main() -> None:
    """Application entry point: configure services, initialize DB, and run polling."""
    validate_config()
    await init_db()

    bot = Bot(
        token=BOT_TOKEN or "dummy_token_for_validation_only",
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    worker_task = asyncio.create_task(monitoring_worker(bot))
    logger.info("Bot dispatcher initialized. Starting polling...")

    try:
        await dp.start_polling(bot)
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        logger.info("Bot session closed.")


if __name__ == "__main__":
    asyncio.run(main())
