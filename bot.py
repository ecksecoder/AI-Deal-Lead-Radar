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
    get_radar_stats,
    get_source_by_id,
    get_user_sources,
    init_db,
    is_item_seen,
    save_item,
    toggle_source,
    update_item_status,
    update_source_checked,
)
from exporter import cleanup_export, export_items_to_csv
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


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Build the persistent bottom control panel."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📡 Мои источники"),
                KeyboardButton(text="➕ Добавить источник"),
            ],
            [
                KeyboardButton(text="⚡ Демо-прогон (Тест радара)"),
                KeyboardButton(text="📊 Скачать отчёт (Excel/CSV)"),
            ],
        ],
        resize_keyboard=True,
    )


def format_alert_card(
    title: str,
    source_name: str,
    category: str,
    score: int,
    summary: str,
    url: str,
    item_id: int,
    status: str = "NEW",
) -> tuple[str, InlineKeyboardMarkup]:
    """Render an HTML alert card with interactive Micro-CRM inline buttons."""
    badges = {
        "HOT_LEAD": f"🔥 <b>HOT_LEAD [{score}/100]</b>",
        "HIGH_VALUE": f"💎 <b>HIGH_VALUE [{score}/100]</b>",
        "STANDARD": f"📌 <b>STANDARD [{score}/100]</b>",
        "LOW_PRIORITY": f"💤 <b>LOW_PRIORITY [{score}/100]</b>",
    }
    badge_header = badges.get(category, f"⚡ <b>LEAD [{score}/100]</b>")

    text = (
        f"{badge_header}\n\n"
        f"💼 <b>{html.escape(title)}</b>\n"
        f"📡 <i>Источник: {html.escape(source_name)}</i>\n\n"
        f"💡 <b>AI Резюме:</b>\n"
        f"{html.escape(summary)}\n\n"
        f"📊 <i>Статус: {status}</i>"
    )

    save_label = "✅ В избранном" if status == "SAVED" else "⭐ В избранное"
    arch_label = "📦 В архиве" if status == "ARCHIVED" else "📥 В архив"

    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=save_label, callback_data=f"crm:save:{item_id}"),
            InlineKeyboardButton(text=arch_label, callback_data=f"crm:arch:{item_id}"),
        ]
    ]

    if url.startswith(("http://", "https://")):
        buttons.append([InlineKeyboardButton(text="🔗 Открыть источник", url=url)])

    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start command and render executive dashboard metrics."""
    await state.clear()
    user_id = message.from_user.id if message.from_user else 0

    if not is_authorized(user_id):
        logger.warning("Unauthorized access attempt by user %d", user_id)
        await message.answer(
            f"⛔ <b>Доступ ограничен (RBAC).</b>\n"
            f"Ваш Telegram ID: <code>{user_id}</code>.\n"
            f"Для авторизации добавьте ID в переменную <code>ADMIN_IDS</code> файла .env."
        )
        return

    stats = await get_radar_stats(user_id)
    text = (
        "🎯 <b>AI Deal & Lead Radar | Панель управления</b>\n\n"
        "Система круглосуточного автономного мониторинга тендеров, "
        "фриланс-заказов и B2B-сделок с нейросетевым скорингом.\n\n"
        f"📡 <b>Активных источников:</b> {stats['active_sources']}\n"
        f"📑 <b>Всего проанализировано:</b> {stats['total_items']}\n"
        f"🔥 <b>Найдено Hot Leads:</b> {stats['hot_leads']}\n"
        f"⭐ <b>В избранном:</b> {stats['saved_items']}\n\n"
        "<i>Используйте кнопки меню ниже для управления источниками и выгрузки отчётов:</i>"
    )
    await message.answer(text, reply_markup=get_main_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Display help information and command directory."""
    text = (
        "📖 <b>Справочник команд AI Deal Radar:</b>\n\n"
        "• /start — Главная панель и метрики\n"
        "• /demo — Запуск тестового демо-прогона (3 реальных лида)\n"
        "• /sources — Список ваших источников мониторинга\n"
        "• /add — Добавить новый RSS/HTML/Demo источник\n"
        "• /export — Скачать Excel/CSV отчёт с UTF-8 BOM\n"
        "• /help — Данная справка"
    )
    await message.answer(text)


@router.message(F.text.in_({"⚡ Демо-прогон (Тест радара)", "/demo"}))
async def handle_demo_run(message: Message) -> None:
    """Simulate live ingestion of 3 realistic B2B leads with instant scoring and alert cards."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_authorized(user_id):
        await message.answer("⛔ Доступ ограничен.")
        return

    status_msg = await message.answer("🚀 <b>Запуск демо-прогона...</b>\nСимулируем поступление 3 B2B-лидов и запуск AI-скоринга...")

    # Ensure demo source exists for this user
    sources = await get_user_sources(user_id)
    demo_source = next((s for s in sources if s["source_type"] == "demo"), None)
    if not demo_source:
        demo_id = await add_source(
            user_id=user_id,
            name="Демо-поток B2B",
            url="internal://demo-feed",
            source_type="demo",
            keywords="python, bot, ai, automation, scraping, llm",
        )
    else:
        demo_id = demo_source["id"]

    demo_items = generate_demo_items("python, bot, ai, automation, scraping, llm")
    cards_sent = 0

    for item in demo_items:
        # Check if already seen
        seen = await is_item_seen(item["item_hash"])
        if not seen:
            scored = await score_item(
                title=item["title"],
                snippet=item["raw_snippet"],
                keywords="python, bot, ai, automation, scraping, llm",
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
                status="NEW",
            )
            card_text, card_markup = format_alert_card(
                title=item["title"],
                source_name="Демо-поток B2B",
                category=scored["category"],
                score=scored["score"],
                summary=scored["summary"],
                url=item["url"],
                item_id=item_id,
                status="NEW",
            )
        else:
            # If item was already saved in previous demo test, score and show card
            scored = await score_item(
                title=item["title"],
                snippet=item["raw_snippet"],
                keywords="python, bot, ai, automation, scraping, llm",
            )
            card_text, card_markup = format_alert_card(
                title=item["title"],
                source_name="Демо-поток B2B",
                category=scored["category"],
                score=scored["score"],
                summary=scored["summary"],
                url=item["url"],
                item_id=1,
                status="NEW",
            )

        await message.answer(card_text, reply_markup=card_markup)
        cards_sent += 1
        await asyncio.sleep(0.3)

    await status_msg.edit_text(
        f"✅ <b>Демо-прогон успешно завершён!</b>\n"
        f"Обработано и выведено карточек: <b>{cards_sent}</b>.\n"
        f"Все записи сохранены в базе SQLite WAL. Нажмите <b>📊 Скачать отчёт (Excel/CSV)</b> для экспорта."
    )


@router.message(F.text.in_({"📡 Мои источники", "/sources"}))
async def handle_list_sources(message: Message) -> None:
    """Display user's configured monitoring sources with inline controls."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_authorized(user_id):
        await message.answer("⛔ Доступ ограничен.")
        return

    sources = await get_user_sources(user_id)
    if not sources:
        await message.answer(
            "📭 <b>У вас пока нет настроенных источников.</b>\n\n"
            "Нажмите <b>➕ Добавить источник</b> или запустите <b>⚡ Демо-прогон</b> для тестирования.",
            reply_markup=get_main_keyboard(),
        )
        return

    await message.answer(f"📡 <b>Ваши источники мониторинга ({len(sources)}):</b>")

    for src in sources:
        status_text = "🟢 Активен" if src["is_active"] else "⏸ На паузе"
        toggle_label = "⏸ Пауза" if src["is_active"] else "▶️ Запустить"
        last_check = src["last_checked_at"] or "Ещё не проверялся"
        if "T" in last_check:
            last_check = last_check.split("T")[0] + " " + last_check.split("T")[1][:5]

        info_text = (
            f"<b>{html.escape(src['name'])}</b> [{status_text}]\n"
            f"Тип: <code>{src['source_type'].upper()}</code>\n"
            f"URL: <code>{html.escape(src['url'])}</code>\n"
            f"Ключевые слова: <i>{html.escape(src['keywords'] or 'Все')}</i>\n"
            f"Последняя проверка: <i>{last_check}</i>"
        )

        buttons = [
            [
                InlineKeyboardButton(
                    text=toggle_label,
                    callback_data=f"src:toggle:{src['id']}",
                ),
                InlineKeyboardButton(
                    text="🔄 Проверить",
                    callback_data=f"src:check:{src['id']}",
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
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
    source_id = int(callback.data.split(":")[2])
    new_state = await toggle_source(source_id)
    state_desc = "активирован" if new_state else "поставлен на паузу"
    await callback.answer(f"Источник {state_desc}!")

    src = await get_source_by_id(source_id)
    if src and callback.message and isinstance(callback.message, Message):
        status_text = "🟢 Активен" if new_state else "⏸ На паузе"
        toggle_label = "⏸ Пауза" if new_state else "▶️ Запустить"
        last_check = src["last_checked_at"] or "Ещё не проверялся"

        info_text = (
            f"<b>{html.escape(src['name'])}</b> [{status_text}]\n"
            f"Тип: <code>{src['source_type'].upper()}</code>\n"
            f"URL: <code>{html.escape(src['url'])}</code>\n"
            f"Ключевые слова: <i>{html.escape(src['keywords'] or 'Все')}</i>\n"
            f"Последняя проверка: <i>{last_check}</i>"
        )
        buttons = [
            [
                InlineKeyboardButton(
                    text=toggle_label,
                    callback_data=f"src:toggle:{src['id']}",
                ),
                InlineKeyboardButton(
                    text="🔄 Проверить",
                    callback_data=f"src:check:{src['id']}",
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
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
    source_id = int(callback.data.split(":")[2])
    await delete_source(source_id)
    await callback.answer("Источник удален.")
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text("🗑 <b>Источник успешно удален.</b>")


@router.callback_query(F.data.startswith("src:check:"))
async def cb_check_source(callback: CallbackQuery) -> None:
    """Trigger an immediate scraping cycle for a single source."""
    if not callback.data:
        return
    source_id = int(callback.data.split(":")[2])
    src = await get_source_by_id(source_id)
    if not src:
        await callback.answer("Источник не найден.")
        return

    await callback.answer("Запущен сбор данных...")
    items = await scrape_source(src)
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
            )
            await callback.message.answer(card_text, reply_markup=card_markup)

    await update_source_checked(source_id)
    if callback.message:
        await callback.message.answer(
            f"✅ Проверка <b>{html.escape(src['name'])}</b> завершена.\n"
            f"Найдено новых элементов: <b>{new_count}</b>, отправлено алертов: <b>{alert_count}</b>."
        )


@router.callback_query(F.data.startswith("crm:"))
async def cb_crm_action(callback: CallbackQuery) -> None:
    """Handle Micro-CRM lead actions (save to favorites, archive)."""
    if not callback.data:
        return
    parts = callback.data.split(":")
    action = parts[1]
    item_id = int(parts[2])

    if action == "save":
        await update_item_status(item_id, "SAVED")
        await callback.answer("⭐ Сохранено в избранное!")
        # Update button visual
        if callback.message and callback.message.reply_markup:
            rows = callback.message.reply_markup.inline_keyboard
            new_rows = []
            for row in rows:
                new_row = []
                for btn in row:
                    if btn.callback_data == callback.data:
                        new_row.append(
                            InlineKeyboardButton(
                                text="✅ В избранном",
                                callback_data=btn.callback_data,
                            )
                        )
                    else:
                        new_row.append(btn)
                new_rows.append(new_row)
            await callback.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=new_rows)
            )

    elif action == "arch":
        await update_item_status(item_id, "ARCHIVED")
        await callback.answer("📥 Отправлено в архив!")
        if callback.message and callback.message.reply_markup:
            rows = callback.message.reply_markup.inline_keyboard
            new_rows = []
            for row in rows:
                new_row = []
                for btn in row:
                    if btn.callback_data == callback.data:
                        new_row.append(
                            InlineKeyboardButton(
                                text="📦 В архиве",
                                callback_data=btn.callback_data,
                            )
                        )
                    else:
                        new_row.append(btn)
                new_rows.append(new_row)
            await callback.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=new_rows)
            )


@router.message(F.text.in_({"➕ Добавить источник", "/add"}))
async def handle_add_source_start(message: Message, state: FSMContext) -> None:
    """Begin FSM wizard for adding a new monitoring source."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_authorized(user_id):
        await message.answer("⛔ Доступ ограничен.")
        return

    buttons = [
        [
            InlineKeyboardButton(text="🌐 RSS / Atom лента", callback_data="add_type:rss"),
            InlineKeyboardButton(text="📄 Веб-страница (HTML)", callback_data="add_type:html"),
        ],
        [
            InlineKeyboardButton(text="🧪 Демо-генератор", callback_data="add_type:demo"),
        ],
    ]
    await state.set_state(AddSourceState.waiting_for_type)
    await message.answer(
        "<b>Шаг 1 из 3:</b> Выберите тип добавляемого источника:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("add_type:"), AddSourceState.waiting_for_type)
async def cb_add_source_type(callback: CallbackQuery, state: FSMContext) -> None:
    """Process selected source type and transition to URL input."""
    if not callback.data:
        return
    stype = callback.data.split(":")[1]
    await state.update_data(source_type=stype)

    if stype == "demo":
        await state.update_data(url="internal://demo-feed")
        await state.set_state(AddSourceState.waiting_for_name)
        await callback.answer()
        if callback.message:
            await callback.message.answer(
                "<b>Шаг 2 из 3:</b> Введите понятное название для демо-источника\n"
                "(например: <i>Демо-поток B2B проектов</i>):"
            )
    else:
        await state.set_state(AddSourceState.waiting_for_url)
        await callback.answer()
        if callback.message:
            await callback.message.answer(
                "<b>Шаг 2 из 4:</b> Введите целевой URL (начиная с <code>http://</code> или <code>https://</code>):"
            )


@router.message(AddSourceState.waiting_for_url)
async def handle_add_source_url(message: Message, state: FSMContext) -> None:
    """Validate submitted URL against SSRF and advance to source name input."""
    url = (message.text or "").strip()
    safe, reason = is_safe_url(url)
    if not safe:
        await message.answer(
            f"❌ <b>Недопустимый или небезопасный URL:</b> {reason}\n"
            "Пожалуйста, введите корректный публичный HTTP/HTTPS адрес:"
        )
        return

    await state.update_data(url=url)
    await state.set_state(AddSourceState.waiting_for_name)
    await message.answer(
        "<b>Шаг 3 из 4:</b> Введите понятное имя источника\n"
        "(например: <i>Хабр Фриланс Python</i> или <i>Upwork B2B Feed</i>):"
    )


@router.message(AddSourceState.waiting_for_name)
async def handle_add_source_name(message: Message, state: FSMContext) -> None:
    """Store source name and prompt for evaluation criteria."""
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не может быть пустым. Пожалуйста, введите название:")
        return

    await state.update_data(name=name)
    await state.set_state(AddSourceState.waiting_for_keywords)
    await message.answer(
        "<b>Шаг 4 из 4:</b> Введите целевые ключевые слова через запятую для AI-скоринга\n"
        "(например: <code>python, bot, scraping, automation, urgent</code>)\n"
        "<i>Или отправьте <b>-</b>, чтобы принимать все лиды:</i>"
    )


@router.message(AddSourceState.waiting_for_keywords)
async def handle_add_source_keywords(message: Message, state: FSMContext) -> None:
    """Save completed source configuration to database."""
    user_id = message.from_user.id if message.from_user else 0
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
        f"🎉 <b>Источник успешно добавлен!</b>\n\n"
        f"ID: <code>{source_id}</code>\n"
        f"Имя: <b>{html.escape(data['name'])}</b>\n"
        f"Тип: <code>{data['source_type'].upper()}</code>\n"
        f"Ключи: <i>{html.escape(keywords or 'Все')}</i>\n\n"
        "Фоновый радар начнёт автоматический сбор. Вы также можете нажать кнопку ниже для немедленной проверки.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Проверить прямо сейчас",
                        callback_data=f"src:check:{source_id}",
                    )
                ]
            ]
        ),
    )


@router.message(F.text.in_({"📊 Скачать отчёт (Excel/CSV)", "/export"}))
async def handle_export_report(message: Message) -> None:
    """Generate and dispatch an Excel-compatible CSV report with UTF-8 BOM."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_authorized(user_id):
        await message.answer("⛔ Доступ ограничен.")
        return

    status_msg = await message.answer("⏳ <b>Формирование Excel-совместимого отчёта...</b>")

    export_path: str = ""
    try:
        export_path = await export_items_to_csv(user_id=user_id)
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        input_file = FSInputFile(export_path, filename=f"radar_leads_{now_str}.csv")
        await message.answer_document(
            input_file,
            caption=(
                "📊 <b>Выгрузка AI Deal & Lead Radar</b>\n\n"
                "• Кодировка: <b>UTF-8 with BOM</b> (нативно открывается в Excel)\n"
                "• Разделитель колонок: <b>точка с запятой (;)</b>\n"
                "• Содержит полные метаданные, AI-оценку и исполнительное резюме."
            ),
        )
        await status_msg.delete()
    except Exception as exc:
        logger.error("Failed to generate or send export: %s", exc)
        await status_msg.edit_text(f"❌ <b>Ошибка при формировании отчёта:</b> {exc}")
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
                    items = await scrape_source(src)
                    for item in items:
                        seen = await is_item_seen(item["item_hash"])
                        if seen:
                            continue

                        scored = await score_item(
                            title=item["title"],
                            snippet=item["raw_snippet"],
                            keywords=src.get("keywords", ""),
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
                            )
                            try:
                                await bot.send_message(
                                    chat_id=src["user_id"],
                                    text=card_text,
                                    reply_markup=card_markup,
                                )
                            except Exception as send_exc:
                                logger.warning(
                                    "Failed to send alert to user %d: %s",
                                    src["user_id"],
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
