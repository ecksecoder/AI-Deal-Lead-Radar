"""Localization module for AI Deal & Lead Radar.

Provides trilingual (EN/UK/RU) string dictionary, automatic locale detection
from Telegram client language code, safe string resolution with fallback,
dynamic language selection inline keyboards, and localized report headers.
"""

from typing import Any
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Onboarding & Language selection
        "onboarding_banner": "🌐 <b>Choose interface language / Оберіть мову інтерфейсу / Выберите язык интерфейса:</b>",
        "choose_language": "🌐 <b>Choose interface language / Оберіть мову інтерфейсу / Выберите язык интерфейса:</b>",
        "language_changed": "✅ <b>Language successfully changed to English 🇬🇧!</b>",
        "language_changed_auto": "✅ <b>Language set to Auto (Telegram client sync) 🔄!</b>",
        "menu_refreshed": "📋 Main menu updated.",
        "btn_lang_en": "English 🇬🇧",
        "btn_lang_uk": "Українська 🇺🇦",
        "btn_lang_ru": "Русский 🇷🇺",
        "btn_lang_auto": "🔄 Auto (Telegram)",
        # Main menu buttons
        "btn_sources": "📡 My Sources",
        "btn_add_source": "➕ Add Source",
        "btn_demo": "⚡ Demo Run",
        "btn_export": "📊 Download Report",
        "btn_lang": "🌐 Change Language",
        "btn_language": "🌐 Change Language",
        # Access control & General
        "unauthorized": (
            "⛔ <b>Access Restricted (RBAC).</b>\n"
            "Your Telegram ID: <code>{user_id}</code>.\n"
            "To authorize, add your ID to the <code>ADMIN_IDS</code> variable in the .env file."
        ),
        "access_restricted": "⛔ Access restricted.",
        # Start & Help
        "start_dashboard": (
            "🎯 <b>AI Deal & Lead Radar | Control Panel</b>\n\n"
            "24/7 autonomous monitoring system for tenders, freelance projects, "
            "and B2B deals with neural scoring.\n\n"
            "📡 <b>Active sources:</b> {active_sources}\n"
            "📑 <b>Total analyzed:</b> {total_items}\n"
            "🔥 <b>Hot Leads found:</b> {hot_leads}\n"
            "⭐ <b>In bookmarks:</b> {saved_items}\n\n"
            "<i>Use the menu buttons below to manage sources and export reports:</i>"
        ),
        "help_text": (
            "📖 <b>AI Deal Radar Command Directory:</b>\n\n"
            "• /start — Main dashboard and metrics\n"
            "• /demo — Run test demo cycle (3 realistic leads)\n"
            "• /sources — List your monitoring sources\n"
            "• /add — Add new RSS/HTML/Demo source\n"
            "• /export — Download Excel/CSV report with UTF-8 BOM\n"
            "• /lang — Switch interface language\n"
            "• /help — This help reference"
        ),
        # Demo run
        "demo_starting": "🚀 <b>Starting demo run...</b>\nSimulating 3 B2B leads ingestion and launching AI scoring...",
        "demo_feed_name": "Demo B2B Feed",
        "demo_completed": (
            "✅ <b>Demo run completed successfully!</b>\n"
            "Processed and displayed cards: <b>{cards_sent}</b>.\n"
            "All entries saved to SQLite WAL database. Click <b>📊 Download Report</b> to export."
        ),
        # Alert cards & Micro-CRM
        "lead_alert_header": "⚡ <b>New Lead Found!</b>",
        "alert_source": "📡 <i>Source: {source_name}</i>",
        "alert_ai_summary": "💡 <b>AI Summary:</b>",
        "alert_status": "📊 <i>Status: {status}</i>",
        "badge_hot_lead": "🔥 <b>HOT_LEAD [{score}/100]</b>",
        "badge_high_value": "💎 <b>HIGH_VALUE [{score}/100]</b>",
        "badge_standard": "📌 <b>STANDARD [{score}/100]</b>",
        "badge_low_priority": "💤 <b>LOW_PRIORITY [{score}/100]</b>",
        "badge_lead": "⚡ <b>{category} [{score}/100]</b>",
        "status_new": "NEW",
        "status_saved": "BOOKMARKED",
        "status_archived": "IGNORED",
        "card_btn_saved": "✅ Bookmarked",
        "card_btn_save": "⭐ Bookmark",
        "card_btn_archived": "❌ Ignored",
        "card_btn_archive": "❌ Ignore",
        "btn_bookmark_idle": "⭐ Bookmark",
        "btn_bookmark_active": "✅ Saved",
        "btn_ignore_idle": "🗑️ Ignore",
        "btn_ignore_active": "❌ Ignored",
        "card_btn_open": "🔗 Open Source",
        "crm_saved_toast": "⭐ Lead bookmarked!",
        "crm_archived_toast": "❌ Lead ignored!",
        # Sources management
        "sources_empty": (
            "📭 <b>You have no configured sources yet.</b>\n\n"
            "Click <b>➕ Add Source</b> or launch <b>⚡ Demo Run</b> to test."
        ),
        "sources_header": "📡 <b>Your monitoring sources ({count}):</b>",
        "source_status_active": "🟢 Active",
        "source_status_paused": "⏸ Paused",
        "source_btn_pause": "⏸ Pause",
        "source_btn_start": "▶️ Start",
        "source_btn_check": "🔄 Check",
        "source_btn_delete": "🗑 Delete",
        "source_not_checked": "Not checked yet",
        "source_all_keywords": "All",
        "source_card_info": (
            "<b>{name}</b> [{status}]\n"
            "Type: <code>{type}</code>\n"
            "URL: <code>{url}</code>\n"
            "Keywords: <i>{keywords}</i>\n"
            "Last check: <i>{last_check}</i>"
        ),
        "source_toggled_active": "Source activated!",
        "source_toggled_paused": "Source paused!",
        "source_deleted_toast": "Source deleted.",
        "source_deleted_msg": "🗑 <b>Source deleted successfully.</b>",
        "source_not_found": "Source not found.",
        "source_check_started": "Data collection started...",
        "source_check_done": (
            "✅ Check of <b>{name}</b> completed.\n"
            "New items found: <b>{new_count}</b>, alerts sent: <b>{alert_count}</b>."
        ),
        # Add source wizard
        "add_step_1": "<b>Step 1 of 3:</b> Choose the source type to add:",
        "add_type_rss": "🌐 RSS / Atom Feed",
        "add_type_html": "📄 Webpage (HTML)",
        "add_type_demo": "🧪 Demo Generator",
        "add_step_demo_name": (
            "<b>Step 2 of 3:</b> Enter a recognizable name for the demo source\n"
            "(e.g.: <i>B2B Demo Projects Feed</i>):"
        ),
        "add_step_url": "<b>Step 2 of 4:</b> Enter the target URL (starting with <code>http://</code> or <code>https://</code>):",
        "add_invalid_url": (
            "❌ <b>Invalid or unsafe URL:</b> {reason}\n"
            "Please enter a valid public HTTP/HTTPS address:"
        ),
        "add_step_name": (
            "<b>Step 3 of 4:</b> Enter a recognizable name for the source\n"
            "(e.g.: <i>Freelance Python Leads</i> or <i>Upwork B2B Feed</i>):"
        ),
        "add_empty_name": "Name cannot be empty. Please enter a name:",
        "add_step_keywords": (
            "<b>Step 4 of 4:</b> Enter target comma-separated keywords for AI scoring\n"
            "(e.g.: <code>python, bot, scraping, automation, urgent</code>)\n"
            "<i>Or send <b>-</b> to accept all leads:</i>"
        ),
        "add_success": (
            "🎉 <b>Source added successfully!</b>\n\n"
            "ID: <code>{source_id}</code>\n"
            "Name: <b>{name}</b>\n"
            "Type: <code>{type}</code>\n"
            "Keywords: <i>{keywords}</i>\n\n"
            "Background radar will start automated scraping. You can also click the button below to check immediately."
        ),
        "btn_check_now": "🔄 Check right now",
        # Export
        "export_preparing": "⏳ <b>Generating Excel-compatible report...</b>",
        "export_batch_separator": "--- Export Batch: {datetime} ({count} items) ---",
        "export_caption": (
            "📊 <b>AI Deal & Lead Radar Export</b>\n\n"
            "• Encoding: <b>UTF-8 with BOM</b> (opens natively in Excel)\n"
            "• Column separator: <b>semicolon (;)</b>\n"
            "• Contains full metadata, AI evaluation, and executive summary."
        ),
        "export_error": "❌ <b>Error generating report:</b> {error}",
        # Report columns
        "col_id": "ID",
        "col_date": "Date",
        "col_source": "Source",
        "col_category": "Category",
        "col_score": "Score",
        "col_title": "Title",
        "col_summary": "Summary",
        "col_status": "Status",
        "col_url": "URL",
    },
    "uk": {
        # Onboarding & Language selection
        "onboarding_banner": "🌐 <b>Оберіть мову інтерфейсу / Choose interface language / Выберите язык интерфейса:</b>",
        "choose_language": "🌐 <b>Оберіть мову інтерфейсу / Choose interface language / Выберите язык интерфейса:</b>",
        "language_changed": "✅ <b>Мову успішно змінено на Українську 🇺🇦!</b>",
        "language_changed_auto": "✅ <b>Мову встановлено в Авто (синхронізація з Telegram) 🔄!</b>",
        "menu_refreshed": "📋 Головне меню оновлено.",
        "btn_lang_en": "English 🇬🇧",
        "btn_lang_uk": "Українська 🇺🇦",
        "btn_lang_ru": "Русский 🇷🇺",
        "btn_lang_auto": "🔄 Автоматично (Telegram)",
        # Main menu buttons
        "btn_sources": "📡 Мої джерела",
        "btn_add_source": "➕ Додати джерело",
        "btn_demo": "⚡ Демо-прогін",
        "btn_export": "📊 Завантажити звіт",
        "btn_lang": "🌐 Змінити мову",
        "btn_language": "🌐 Змінити мову",
        # Access control & General
        "unauthorized": (
            "⛔ <b>Доступ обмежено (RBAC).</b>\n"
            "Ваш Telegram ID: <code>{user_id}</code>.\n"
            "Для авторизації додайте ваш ID до змінної <code>ADMIN_IDS</code> у файлі .env."
        ),
        "access_restricted": "⛔ Доступ обмежено.",
        # Start & Help
        "start_dashboard": (
            "🎯 <b>AI Deal & Lead Radar | Панель керування</b>\n\n"
            "Система цілодобового автономного моніторингу тендерів, "
            "фриланс-проєктів та B2B-угод з нейромережевим скорингом.\n\n"
            "📡 <b>Активних джерел:</b> {active_sources}\n"
            "📑 <b>Всього проаналізовано:</b> {total_items}\n"
            "🔥 <b>Знайдено Hot Leads:</b> {hot_leads}\n"
            "⭐ <b>В закладках:</b> {saved_items}\n\n"
            "<i>Використовуйте кнопки меню нижче для керування джерелами та експорту звітів:</i>"
        ),
        "help_text": (
            "📖 <b>Довідник команд AI Deal Radar:</b>\n\n"
            "• /start — Головна панель та метрики\n"
            "• /demo — Запуск тестового демо-прогону (3 реальних ліди)\n"
            "• /sources — Список ваших джерел моніторингу\n"
            "• /add — Додати нове RSS/HTML/Demo джерело\n"
            "• /export — Завантажити Excel/CSV звіт з UTF-8 BOM\n"
            "• /lang — Змінити мову інтерфейсу\n"
            "• /help — Ця довідка"
        ),
        # Demo run
        "demo_starting": "🚀 <b>Запуск демо-прогону...</b>\nСимулюємо надходження 3 B2B-лідів та запуск AI-скорингу...",
        "demo_feed_name": "Демо-потік B2B",
        "demo_completed": (
            "✅ <b>Демо-прогін успішно завершено!</b>\n"
            "Оброблено та виведено карток: <b>{cards_sent}</b>.\n"
            "Усі записи збережено в базі SQLite WAL. Натисніть <b>📊 Завантажити звіт</b> для експорту."
        ),
        # Alert cards & Micro-CRM
        "lead_alert_header": "⚡ <b>Знайдено новий лід!</b>",
        "alert_source": "📡 <i>Джерело: {source_name}</i>",
        "alert_ai_summary": "💡 <b>AI Резюме:</b>",
        "alert_status": "📊 <i>Статус: {status}</i>",
        "badge_hot_lead": "🔥 <b>HOT_LEAD [{score}/100]</b>",
        "badge_high_value": "💎 <b>HIGH_VALUE [{score}/100]</b>",
        "badge_standard": "📌 <b>STANDARD [{score}/100]</b>",
        "badge_low_priority": "💤 <b>LOW_PRIORITY [{score}/100]</b>",
        "badge_lead": "⚡ <b>{category} [{score}/100]</b>",
        "status_new": "НОВИЙ",
        "status_saved": "В ЗАКЛАДКАХ",
        "status_archived": "ПРОПУЩЕНО",
        "card_btn_saved": "✅ В закладках",
        "card_btn_save": "⭐ В закладки",
        "card_btn_archived": "❌ Пропущено",
        "card_btn_archive": "❌ Пропустити",
        "btn_bookmark_idle": "⭐ До закладок",
        "btn_bookmark_active": "✅ У закладках",
        "btn_ignore_idle": "🗑️ Пропустити",
        "btn_ignore_active": "❌ Пропущено",
        "card_btn_open": "🔗 Відкрити джерело",
        "crm_saved_toast": "⭐ Лід додано в закладки!",
        "crm_archived_toast": "❌ Лід пропущено!",
        # Sources management
        "sources_empty": (
            "📭 <b>У вас ще немає налаштованих джерел.</b>\n\n"
            "Натисніть <b>➕ Додати джерело</b> або запустіть <b>⚡ Демо-прогін</b> для тестування."
        ),
        "sources_header": "📡 <b>Ваші джерела моніторингу ({count}):</b>",
        "source_status_active": "🟢 Активне",
        "source_status_paused": "⏸ На паузі",
        "source_btn_pause": "⏸ Пауза",
        "source_btn_start": "▶️ Запустити",
        "source_btn_check": "🔄 Перевірити",
        "source_btn_delete": "🗑 Видалити",
        "source_not_checked": "Ще не перевірялося",
        "source_all_keywords": "Усі",
        "source_card_info": (
            "<b>{name}</b> [{status}]\n"
            "Тип: <code>{type}</code>\n"
            "URL: <code>{url}</code>\n"
            "Ключові слова: <i>{keywords}</i>\n"
            "Остання перевірка: <i>{last_check}</i>"
        ),
        "source_toggled_active": "Джерело активовано!",
        "source_toggled_paused": "Джерело призупинено!",
        "source_deleted_toast": "Джерело видалено.",
        "source_deleted_msg": "🗑 <b>Джерело успішно видалено.</b>",
        "source_not_found": "Джерело не знайдено.",
        "source_check_started": "Збір даних розпочато...",
        "source_check_done": (
            "✅ Перевірку <b>{name}</b> завершено.\n"
            "Знайдено нових елементів: <b>{new_count}</b>, надіслано сповіщень: <b>{alert_count}</b>."
        ),
        # Add source wizard
        "add_step_1": "<b>Крок 1 з 3:</b> Оберіть тип джерела для додавання:",
        "add_type_rss": "🌐 RSS / Atom стрічка",
        "add_type_html": "📄 Веб-сторінка (HTML)",
        "add_type_demo": "🧪 Демо-генератор",
        "add_step_demo_name": (
            "<b>Крок 2 з 3:</b> Введіть зрозумілу назву для демо-джерела\n"
            "(наприклад: <i>Демо-потік B2B проєктів</i>):"
        ),
        "add_step_url": "<b>Крок 2 з 4:</b> Введіть цільовий URL (починаючи з <code>http://</code> або <code>https://</code>):",
        "add_invalid_url": (
            "❌ <b>Неприпустимий або небезпечний URL:</b> {reason}\n"
            "Будь ласка, введіть коректну публічну HTTP/HTTPS адресу:"
        ),
        "add_step_name": (
            "<b>Крок 3 з 4:</b> Введіть зрозумілу назву джерела\n"
            "(наприклад: <i>Фриланс Python замовлення</i> або <i>Upwork B2B Feed</i>):"
        ),
        "add_empty_name": "Назва не може бути порожньою. Будь ласка, введіть назву:",
        "add_step_keywords": (
            "<b>Крок 4 з 4:</b> Введіть цільові ключові слова через кому для AI-скорингу\n"
            "(наприклад: <code>python, bot, scraping, automation, urgent</code>)\n"
            "<i>Або надішліть <b>-</b>, щоб приймати всі ліди:</i>"
        ),
        "add_success": (
            "🎉 <b>Джерело успішно додано!</b>\n\n"
            "ID: <code>{source_id}</code>\n"
            "Назва: <b>{name}</b>\n"
            "Тип: <code>{type}</code>\n"
            "Ключі: <i>{keywords}</i>\n\n"
            "Фоновий радар розпочне автоматичний збір. Ви також можете натиснути кнопку нижче для негайної перевірки."
        ),
        "btn_check_now": "🔄 Перевірити зараз",
        # Export
        "export_preparing": "⏳ <b>Формування Excel-сумісного звіту...</b>",
        "export_batch_separator": "--- Партія вивантаження: {datetime} ({count} записів) ---",
        "export_caption": (
            "📊 <b>Експорт AI Deal & Lead Radar</b>\n\n"
            "• Кодування: <b>UTF-8 with BOM</b> (відкривається в Excel без спотворень)\n"
            "• Роздільник колонок: <b>крапка з комою (;)</b>\n"
            "• Містить повні метадані, AI-оцінку та виконавче резюме."
        ),
        "export_error": "❌ <b>Помилка під час формування звіту:</b> {error}",
        # Report columns
        "col_id": "ID",
        "col_date": "Дата",
        "col_source": "Джерело",
        "col_category": "Категорія",
        "col_score": "Оцінка",
        "col_title": "Заголовок",
        "col_summary": "Резюме",
        "col_status": "Статус",
        "col_url": "URL",
    },
    "ru": {
        # Onboarding & Language selection
        "onboarding_banner": "🌐 <b>Выберите язык интерфейса / Choose interface language / Оберіть мову інтерфейсу:</b>",
        "choose_language": "🌐 <b>Выберите язык интерфейса / Choose interface language / Оберіть мову інтерфейсу:</b>",
        "language_changed": "✅ <b>Язык успешно изменён на Русский 🇷🇺!</b>",
        "language_changed_auto": "✅ <b>Язык установлен в Авто (синхронизация с Telegram) 🔄!</b>",
        "menu_refreshed": "📋 Главное меню обновлено.",
        "btn_lang_en": "English 🇬🇧",
        "btn_lang_uk": "Українська 🇺🇦",
        "btn_lang_ru": "Русский 🇷🇺",
        "btn_lang_auto": "🔄 Авто (Telegram)",
        # Main menu buttons
        "btn_sources": "📡 Мои источники",
        "btn_add_source": "➕ Добавить источник",
        "btn_demo": "⚡ Демо-прогон",
        "btn_export": "📊 Скачать отчёт",
        "btn_lang": "🌐 Сменить язык",
        "btn_language": "🌐 Сменить язык",
        # Access control & General
        "unauthorized": (
            "⛔ <b>Доступ ограничен (RBAC).</b>\n"
            "Ваш Telegram ID: <code>{user_id}</code>.\n"
            "Для авторизации добавьте ID в переменную <code>ADMIN_IDS</code> файла .env."
        ),
        "access_restricted": "⛔ Доступ ограничен.",
        # Start & Help
        "start_dashboard": (
            "🎯 <b>AI Deal & Lead Radar | Панель управления</b>\n\n"
            "Система круглосуточного автономного мониторинга тендеров, "
            "фриланс-заказов и B2B-сделок с нейросетевым скорингом.\n\n"
            "📡 <b>Активных источников:</b> {active_sources}\n"
            "📑 <b>Всего проанализировано:</b> {total_items}\n"
            "🔥 <b>Найдено Hot Leads:</b> {hot_leads}\n"
            "⭐ <b>В закладках:</b> {saved_items}\n\n"
            "<i>Используйте кнопки меню ниже для управления источниками и выгрузки отчётов:</i>"
        ),
        "help_text": (
            "📖 <b>Справочник команд AI Deal Radar:</b>\n\n"
            "• /start — Главная панель и метрики\n"
            "• /demo — Запуск тестового демо-прогона (3 реальных лида)\n"
            "• /sources — Список ваших источников мониторинга\n"
            "• /add — Добавить новый RSS/HTML/Demo источник\n"
            "• /export — Скачать Excel/CSV отчёт с UTF-8 BOM\n"
            "• /lang — Сменить язык интерфейса\n"
            "• /help — Данная справка"
        ),
        # Demo run
        "demo_starting": "🚀 <b>Запуск демо-прогона...</b>\nСимулируем поступление 3 B2B-лидов и запуск AI-скоринга...",
        "demo_feed_name": "Демо-поток B2B",
        "demo_completed": (
            "✅ <b>Демо-прогон успешно завершён!</b>\n"
            "Обработано и выведено карточек: <b>{cards_sent}</b>.\n"
            "Все записи сохранены в базе SQLite WAL. Нажмите <b>📊 Скачать отчёт</b> для экспорта."
        ),
        # Alert cards & Micro-CRM
        "lead_alert_header": "⚡ <b>Найден новый лид!</b>",
        "alert_source": "📡 <i>Источник: {source_name}</i>",
        "alert_ai_summary": "💡 <b>AI Резюме:</b>",
        "alert_status": "📊 <i>Статус: {status}</i>",
        "badge_hot_lead": "🔥 <b>HOT_LEAD [{score}/100]</b>",
        "badge_high_value": "💎 <b>HIGH_VALUE [{score}/100]</b>",
        "badge_standard": "📌 <b>STANDARD [{score}/100]</b>",
        "badge_low_priority": "💤 <b>LOW_PRIORITY [{score}/100]</b>",
        "badge_lead": "⚡ <b>{category} [{score}/100]</b>",
        "status_new": "НОВЫЙ",
        "status_saved": "В ЗАКЛАДКАХ",
        "status_archived": "ПРОПУЩЕНО",
        "card_btn_saved": "✅ В закладках",
        "card_btn_save": "⭐ В закладки",
        "card_btn_archived": "❌ Пропущено",
        "card_btn_archive": "❌ Пропустить",
        "btn_bookmark_idle": "⭐ В закладки",
        "btn_bookmark_active": "✅ В закладках",
        "btn_ignore_idle": "🗑️ Пропустить",
        "btn_ignore_active": "❌ Пропущено",
        "card_btn_open": "🔗 Открыть источник",
        "crm_saved_toast": "⭐ Лид добавлен в закладки!",
        "crm_archived_toast": "❌ Лид пропущен!",
        # Sources management
        "sources_empty": (
            "📭 <b>У вас пока нет настроенных источников.</b>\n\n"
            "Нажмите <b>➕ Добавить источник</b> или запустите <b>⚡ Демо-прогон</b> для тестирования."
        ),
        "sources_header": "📡 <b>Ваши источники мониторинга ({count}):</b>",
        "source_status_active": "🟢 Активен",
        "source_status_paused": "⏸ На паузе",
        "source_btn_pause": "⏸ Пауза",
        "source_btn_start": "▶️ Запустить",
        "source_btn_check": "🔄 Проверить",
        "source_btn_delete": "🗑 Удалить",
        "source_not_checked": "Ещё не проверялся",
        "source_all_keywords": "Все",
        "source_card_info": (
            "<b>{name}</b> [{status}]\n"
            "Тип: <code>{type}</code>\n"
            "URL: <code>{url}</code>\n"
            "Ключевые слова: <i>{keywords}</i>\n"
            "Последняя проверка: <i>{last_check}</i>"
        ),
        "source_toggled_active": "Источник активирован!",
        "source_toggled_paused": "Источник поставлен на паузу!",
        "source_deleted_toast": "Источник удален.",
        "source_deleted_msg": "🗑 <b>Источник успешно удален.</b>",
        "source_not_found": "Источник не найден.",
        "source_check_started": "Запущен сбор данных...",
        "source_check_done": (
            "✅ Проверка <b>{name}</b> завершена.\n"
            "Найдено новых элементов: <b>{new_count}</b>, отправлено алертов: <b>{alert_count}</b>."
        ),
        # Add source wizard
        "add_step_1": "<b>Шаг 1 из 3:</b> Выберите тип добавляемого источника:",
        "add_type_rss": "🌐 RSS / Atom лента",
        "add_type_html": "📄 Веб-страница (HTML)",
        "add_type_demo": "🧪 Демо-генератор",
        "add_step_demo_name": (
            "<b>Шаг 2 из 3:</b> Введите понятное название для демо-источника\n"
            "(например: <i>Демо-поток B2B проектов</i>):"
        ),
        "add_step_url": "<b>Шаг 2 из 4:</b> Введите целевой URL (начиная с <code>http://</code> или <code>https://</code>):",
        "add_invalid_url": (
            "❌ <b>Недопустимый или небезопасный URL:</b> {reason}\n"
            "Пожалуйста, введите корректный публичный HTTP/HTTPS адрес:"
        ),
        "add_step_name": (
            "<b>Шаг 3 из 4:</b> Введите понятное имя источника\n"
            "(например: <i>Фриланс Python заказы</i> или <i>Upwork B2B Feed</i>):"
        ),
        "add_empty_name": "Имя не может быть пустым. Пожалуйста, введите название:",
        "add_step_keywords": (
            "<b>Шаг 4 из 4:</b> Введите целевые ключевые слова через запятую для AI-скоринга\n"
            "(например: <code>python, bot, scraping, automation, urgent</code>)\n"
            "<i>Или отправьте <b>-</b>, чтобы принимать все лиды:</i>"
        ),
        "add_success": (
            "🎉 <b>Источник успешно добавлен!</b>\n\n"
            "ID: <code>{source_id}</code>\n"
            "Имя: <b>{name}</b>\n"
            "Тип: <code>{type}</code>\n"
            "Ключи: <i>{keywords}</i>\n\n"
            "Фоновый радар начнёт автоматический сбор. Вы также можете нажать кнопку ниже для немедленной проверки."
        ),
        "btn_check_now": "🔄 Проверить прямо сейчас",
        # Export
        "export_preparing": "⏳ <b>Формирование Excel-совместимого отчёта...</b>",
        "export_batch_separator": "--- Партия выгрузки: {datetime} ({count} записей) ---",
        "export_caption": (
            "📊 <b>Выгрузка AI Deal & Lead Radar</b>\n\n"
            "• Кодировка: <b>UTF-8 with BOM</b> (нативно открывается в Excel)\n"
            "• Разделитель колонок: <b>точка с запятой (;)</b>\n"
            "• Содержит полные метаданные, AI-оценку и исполнительное резюме."
        ),
        "export_error": "❌ <b>Ошибка при формировании отчёта:</b> {error}",
        # Report columns
        "col_id": "ID",
        "col_date": "Дата",
        "col_source": "Источник",
        "col_category": "Категория",
        "col_score": "Балл",
        "col_title": "Заголовок",
        "col_summary": "Резюме",
        "col_status": "Статус",
        "col_url": "URL",
    },
}


def detect_locale(telegram_lang_code: str | None) -> str:
    """Detect user language code from Telegram client.

    Returns 'uk' if code == 'uk'; returns 'ru' if code in ('ru', 'be'); otherwise returns 'en'.
    """
    if not telegram_lang_code:
        return "en"
    clean_code = telegram_lang_code.lower().strip().split("-")[0].split("_")[0]
    if clean_code == "uk":
        return "uk"
    if clean_code in ("ru", "be"):
        return "ru"
    return "en"


def get_text(key: str, lang: str = "en", **kwargs: Any) -> str:
    """Retrieve localized string with safe fallback to 'en' and kwargs formatting.

    Args:
        key: The translation key identifier.
        lang: Language code ('en', 'uk', or 'ru').
        **kwargs: Substitution variables for string formatting.

    Returns:
        Formatted localized string, falling back to 'en' or the raw key.
    """
    lang_dict = TRANSLATIONS.get(lang) or TRANSLATIONS.get("en", {})
    template = lang_dict.get(key)
    if template is None:
        template = TRANSLATIONS.get("en", {}).get(key, key)

    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template
    return template


def get_button_variants(key: str) -> list[str]:
    """Retrieve all translated string variations for a button across all supported languages."""
    variants: set[str] = set()
    keys = [key]
    if key in ("btn_lang", "btn_language"):
        keys = ["btn_lang", "btn_language"]

    for k in keys:
        for l in ("en", "uk", "ru"):
            val = TRANSLATIONS.get(l, {}).get(k)
            if val:
                variants.add(val)

    # Add common command or legacy label variants
    if key == "btn_demo":
        variants.update({
            "⚡ Demo Run",
            "⚡ Демо-прогін",
            "⚡ Демо-прогон",
            "⚡ Demo Run (Radar Test)",
            "⚡ Демо-прогін (Тест радару)",
            "⚡ Демо-прогон (Тест радара)",
        })
    elif key == "btn_sources":
        variants.update({
            "📡 My Sources",
            "📡 Мої джерела",
            "📡 Мои источники",
        })
    elif key == "btn_add_source":
        variants.update({
            "➕ Add Source",
            "➕ Додати джерело",
            "➕ Добавить источник",
        })
    elif key == "btn_export":
        variants.update({
            "📊 Download Report",
            "📊 Завантажити звіт",
            "📊 Скачать отчёт",
            "📊 Download Report (Excel/CSV)",
            "📊 Завантажити звіт (Excel/CSV)",
            "📊 Скачать отчёт (Excel/CSV)",
        })
    elif key in ("btn_lang", "btn_language"):
        variants.update({
            "🌐 Change Language",
            "🌐 Змінити мову",
            "🌐 Сменить язык",
            "🌐 Language / Мова / Язык",
            "🌐 Мова / Language",
            "🌐 Язык / Language",
        })

    return list(variants)


def get_export_headers(lang: str = "en") -> list[str]:
    """Return localized Excel/CSV column headers (Title, URL, Score, Category, Date, etc.).

    Args:
        lang: Target language code ('en', 'uk', or 'ru').

    Returns:
        List of localized header labels.
    """
    clean_lang = (lang or "en").lower().strip()
    if clean_lang not in TRANSLATIONS:
        clean_lang = "en"

    return [
        get_text("col_id", clean_lang),
        get_text("col_date", clean_lang),
        get_text("col_source", clean_lang),
        get_text("col_category", clean_lang),
        get_text("col_score", clean_lang),
        get_text("col_title", clean_lang),
        get_text("col_summary", clean_lang),
        get_text("col_status", clean_lang),
        get_text("col_url", clean_lang),
    ]


def get_language_inline_kb(
    active_lang: str = "en", is_auto: bool = False, prefix: str = "lang_set"
) -> InlineKeyboardMarkup:
    """Build inline keyboard for language selection with Latin (Telegram) auto-labels and active indicators.

    Args:
        active_lang: Active language code ('en', 'uk', or 'ru').
        is_auto: Whether language is automatically synced with Telegram client.
        prefix: Callback data prefix for language selection actions.

    Returns:
        Configured InlineKeyboardMarkup.
    """
    clean_lang = (active_lang or "en").lower().strip()
    if clean_lang not in ("en", "uk", "ru"):
        clean_lang = "en"

    # Enforce strict Auto button labels with Latin (Telegram)
    auto_labels: dict[str, str] = {
        "en": "🔄 Auto (Telegram)",
        "uk": "🔄 Автоматично (Telegram)",
        "ru": "🔄 Авто (Telegram)",
    }

    en_text = f"✅ English 🇬🇧" if (clean_lang == "en" and not is_auto) else "English 🇬🇧"
    uk_text = f"✅ Українська 🇺🇦" if (clean_lang == "uk" and not is_auto) else "Українська 🇺🇦"
    ru_text = f"✅ Русский 🇷🇺" if (clean_lang == "ru" and not is_auto) else "Русский 🇷🇺"

    base_auto = auto_labels.get(clean_lang, "🔄 Auto (Telegram)")
    auto_text = f"✅ {base_auto}" if is_auto else base_auto

    buttons = [
        [
            InlineKeyboardButton(text=en_text, callback_data=f"{prefix}:en"),
            InlineKeyboardButton(text=uk_text, callback_data=f"{prefix}:uk"),
            InlineKeyboardButton(text=ru_text, callback_data=f"{prefix}:ru"),
        ],
        [
            InlineKeyboardButton(text=auto_text, callback_data=f"{prefix}:auto"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
