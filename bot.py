import logging
import html
import asyncio
import re
import os
import sys
from datetime import datetime, timedelta, time as datetime_time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN, ADMIN_ID
try:
    from config import ADMIN_IDS, GROUP_CHAT_ID as CFG_GROUP
except ImportError:
    ADMIN_IDS = [ADMIN_ID]
    CFG_GROUP = None
from database import Database
from excel_exporter import ExcelExporter
from not_assigned_exporter import NotAssignedExporter
from formatters import *
from utils import *
from templates import get_empty_schedule_template, get_example_schedule, get_schedule_instruction

# Группа из config/.env (fallback — старый тестовый id)
if CFG_GROUP is not None:
    GROUP_CHAT_ID = CFG_GROUP
else:
    GROUP_CHAT_ID = -5056870971

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация
db = Database()
excel_exporter = ExcelExporter()
not_assigned_exporter = NotAssignedExporter()

# Хранилище состояний
user_states = {}
temp_data = {}

def is_admin(uid: int) -> bool:
    try:
        return int(uid) in ADMIN_IDS or int(uid) == int(ADMIN_ID)
    except Exception:
        return int(uid) == int(ADMIN_ID)

async def notify_admins(context, text, parse_mode='HTML', reply_markup=None):
    for aid in (ADMIN_IDS if ADMIN_IDS else [ADMIN_ID]):
        try:
            await context.bot.send_message(chat_id=aid, text=text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"notify_admins {aid}: {e}")

def get_admin_reply_keyboard():
    buttons = [
        ["📊 Все графики", "📅 След. неделя"],
        ["📁 Excel-отчет", "📤 Рассылка"],
        ["🔍 Свободные", "📋 Не назначенные"],
        ["🧹 Очистить графики", "✏️ Редактировать график"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# True = можно слать график в любой день (только для теста)
TEST_ALLOW_SCHEDULE_ANY_DAY = False

def is_schedule_submission_allowed() -> bool:
    """
    Для официанта: пт/сб.
    Если TEST_ALLOW_SCHEDULE_ANY_DAY = True — без ограничения (тест).
    """
    if TEST_ALLOW_SCHEDULE_ANY_DAY:
        return True
    return datetime.now().weekday() in (4, 5)  # 4=пт, 5=сб

def get_submission_window_text() -> str:
    """Текст окна приёма графиков"""
    if TEST_ALLOW_SCHEDULE_ANY_DAY:
        return (
            "🧪 <b>ТЕСТ:</b> график можно отправить в любой день\n"
            "⚠️ <b>Отправить — 1 раз, изменить — тоже только 1 раз</b>"
        )
    return (
        "📅 <b>График можно отправить / изменить только:</b>\n"
        "• Пятница — весь день\n"
        "• Суббота — весь день\n\n"
        "🚫 В воскресенье и в будни — нельзя\n"
        "⚠️ <b>Отправить — 1 раз, изменить — тоже только 1 раз</b>"
    )

def ensure_excel_path(week_start: str = None) -> str:
    """Гарантирует, что у excel_exporter есть валидный file_path"""
    path = getattr(excel_exporter, 'file_path', None)
    if path:
        return path
    if not week_start:
        try:
            week_start = get_week_start_str()
        except Exception:
            week_start = datetime.now().strftime("%Y-%m-%d")
    base_dir = "/tmp/bot_files" if os.name != "nt" else os.path.join(os.getcwd(), "bot_files")
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"schedules_{week_start}.xlsx")
    try:
        excel_exporter.file_path = path
    except Exception:
        pass
    return path

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    await db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    is_admin_user = is_admin(user.id)
    
    current_week = format_week(get_current_week_start(), get_current_week_end())
    next_week = format_week(get_next_week_start(), get_next_week_end())
    
    if is_admin_user:
        keyboard = get_admin_reply_keyboard()
        welcome = (
            "👋 <b>Добрый день, Администратор!</b>\n\n"
            f"{format_header('Панель управления', '📋')}"
            f"📅 Текущая неделя: <b>{current_week}</b>\n"
            f"📅 Следующая неделя: <b>{next_week}</b>\n\n"
            f"{format_info('Выберите действие в меню ниже')}\n\n"
            "💡 <i>Кнопки всегда под рукой</i>"
        )
    else:
        keyboard = get_main_reply_keyboard()
        
        _sch = await db.get_user_schedule(user.id, get_submit_week_start_str())
        has_schedule = _sch is not None and str(_sch).strip() != ""
        
        welcome = (
            "👋 <b>Witaj!</b>\n\n"
            f"{format_header('Panel pracownika', '👤')}"
            f"📅 Następny tydzień: <b>{get_submit_week_range_text()}</b>\n\n"
        )
        
        if not has_schedule:
            welcome += f"{format_info('Вы ещё не отправили график')}\n"
            welcome += "💡 <i>Нажмите «📝 Отправить график»</i>\n\n"
        else:
            welcome += f"{format_success('График уже отправлен')}\n"
            welcome += "⚠️ <i>Можно изменить только один раз</i>\n\n"
        
        welcome += get_submission_window_text()
    
    await update.message.reply_text(
        welcome,
        parse_mode='HTML',
        reply_markup=keyboard
    )

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    
    if chat_type in ['group', 'supergroup']:
        await update.message.reply_text(
            f"{format_header('ID группы', '👥')}"
            f"<code>{chat_id}</code>\n\n"
            f"{format_info('Сохраните этот ID для настройки уведомлений')}",
            parse_mode='HTML'
        )
    else:
        user_id = update.effective_user.id
        await update.message.reply_text(
            f"{format_header('Мой ID', '🆔')}"
            f"<code>{user_id}</code>\n\n"
            f"{format_info('Сохраните этот ID')}",
            parse_mode='HTML'
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin_user = is_admin(user_id)
    
    if is_admin_user:
        text = (
            f"{format_header('Помощь', '❓')}"
            "📌 <b>Доступные действия:</b>\n\n"
            "📊 <b>Все графики</b>\n"
            "  └ Просмотр всех графиков сотрудников\n\n"
            "📁 <b>Excel-отчет</b>\n"
            "  └ Экспорт динамической таблицы\n\n"
            "📤 <b>Рассылка</b>\n"
            "  └ Отправка готового графика\n\n"
            "🔍 <b>Свободные</b>\n"
            "  └ Поиск свободных сотрудников\n\n"
            "📈 <b>Статистика</b>\n"
            "  └ Статистика отправок\n\n"
            "🧹 <b>Очистить графики</b>\n"
            "  └ Удалить все графики официантов (с подтверждением)\n\n"
            "🔄 <b>/restart</b>\n"
            "  └ Перезапустить бота\n\n"
            f"{format_info('Используйте кнопки внизу')}"
        )
    else:
        text = (
            f"{format_header('Pomoc', '❓')}"
            "📌 <b>Dostępne akcje:</b>\n\n"
            "📝 <b>Wyślij grafik</b>\n"
            "  └ Podaj dni i godziny pracy\n\n"
            "📋 <b>Mój grafik</b>\n"
            "  └ Sprawdź swój grafik\n\n"
            f"{get_submission_window_text()}\n\n"
            f"{format_info('Przykład grafiku:')}\n"
            "<code>Poniedziałek: cały dzień</code>\n"
            "<code>Wtorek: od 10:00</code>\n"
            "<code>Środa: do 16:00</code>\n\n"
            f"{format_info('Pamiętaj - podaj dzień tygodnia!')}"
        )
    
    await update.message.reply_text(text, parse_mode='HTML')

async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезапуск бота (только админ) через systemd"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(
            f"{format_error('Доступ запрещен')}",
            parse_mode='HTML'
        )
        return
    
    await update.message.reply_text(
        f"{format_header('Перезапуск', '🔄')}"
        "⏳ <b>Бот перезагружается...</b>\n\n"
        f"{format_info('Через несколько секунд бот снова будет онлайн')}\n"
        "💡 <i>Напишите /start после перезапуска</i>",
        parse_mode='HTML'
    )
    
    logger.info(f"Админ {user_id} запросил /restart")
    await asyncio.sleep(1)
    import subprocess
    subprocess.Popen(['/bin/systemctl', 'restart', 'newaybot'], start_new_session=True)

# ========== НАПОМИНАНИЕ ОБ ОТПРАВКЕ ГРАФИКА ==========

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Напоминание в группу: только пятница и суббота, каждые 6 часов"""
    today = datetime.now().weekday()  # 4=пт, 5=сб
    if today not in (4, 5):
        return
    
    text = (
        "📢 <b>PRZYPOMNIENIE!</b>\n\n"
        f"📅 Następny tydzień: <b>{get_submit_week_range_text()}</b>\n\n"
        f"{format_info('Czas wysłać swój grafik pracy!')}\n"
        "💡 <i>Naciśnij «📝 Отправить график»</i>\n\n"
        "⚠️ Grafik na ten tydzień można wysłać tylko raz"
    )
    
    try:
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=text,
            parse_mode='HTML'
        )
        logger.info(f"Напоминание отправлено в группу {GROUP_CHAT_ID} (день={today})")
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания в группу {GROUP_CHAT_ID}: {e}")

# ========== ОБРАБОТЧИКИ ==========

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass  # кнопка устарела / уже нажата — не падаем
    
    user_id = query.from_user.id
    data = query.data or ""
    
    if data == "main_menu":
        is_admin_user = is_admin(user_id)
        keyboard = get_admin_reply_keyboard() if is_admin_user else get_main_reply_keyboard()

        
        await query.message.delete()
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"{format_header('Главное меню', '🏠')}",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return
    
    # ========== ПОДТВЕРЖДЕНИЕ ОЧИСТКИ ГРАФИКОВ ==========
    if data == "confirm_clear_schedules":
        if not is_admin(user_id):
            await query.edit_message_text(
                f"{format_error('Доступ запрещен')}",
                parse_mode='HTML'
            )
            return
        week_start = (temp_data.get(user_id) or {}).get("clear_week_start")
        week_range = (temp_data.get(user_id) or {}).get("clear_week_range")
        if not week_start:
            await query.edit_message_text(
                f"{format_error('Сначала укажите неделю')}",
                parse_mode='HTML'
            )
            return
        try:
            stats = await db.clear_data_for_week(week_start)
            temp_data.pop(user_id, None)
            await query.edit_message_text(
                f"{format_success('Неделя очищена')}\n\n"
                f"📅 <b>{week_range}</b>\n\n"
                f"🗑 Графики: {stats.get('schedules', 0)}\n"
                f"🗑 Назначения: {stats.get('assigned', 0)}\n"
                f"🗑 Доп. смены: {stats.get('extra_shifts', 0)}\n\n"
                f"{format_info('Другие недели не изменены')}",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Ошибка очистки недели: {e}")
            await query.edit_message_text(
                f"{format_error('Ошибка при очистке')}\n\n{str(e)}",
                parse_mode='HTML'
            )
        return
    
    if data == "cancel_clear_schedules":
        await query.edit_message_text(
            f"{format_info('Очистка отменена')}\n\n"
            "Данные не были изменены.",
            parse_mode='HTML'
        )
        return
    
    # ========== РАССЫЛКА СМЕНЫ ==========
    if data == "broadcast_shift":
        if not is_admin(user_id):
            await query.edit_message_text(
                f"{format_error('Доступ запрещен')}",
                parse_mode='HTML'
            )
            return
        
        if "broadcast_day" not in temp_data.get(user_id, {}):
            await query.edit_message_text(
                f"{format_error('Сначала выполните поиск свободных сотрудников')}",
                parse_mode='HTML'
            )
            return
        
        found_day = temp_data[user_id]["broadcast_day"]
        found_date = temp_data[user_id].get("broadcast_date", "")
        
        user_states[user_id] = "waiting_broadcast_shift_limit"
        temp_data[user_id]["broadcast_day"] = found_day
        temp_data[user_id]["broadcast_date"] = found_date
        
        await query.edit_message_text(
            f"{format_header('Установите лимит сотрудников', '📝')}"
            f"📅 <b>День:</b> {found_day} ({found_date})\n\n"
            f"{format_info('Введите количество сотрудников, которые могут подтвердить смену:')}\n"
            "<b>Пример:</b> <code>3</code>\n\n"
            "ℹ️ <i>После того как нужное количество сотрудников подтвердят смену, остальные не смогут её принять</i>\n\n"
            f"{format_info('Или нажмите «Главное меню» для отмены')}",
            parse_mode='HTML',
            reply_markup=get_main_menu_inline()
        )
        return
    
    # ========== ПОДТВЕРЖДЕНИЕ СМЕНЫ ==========
    if data.startswith("confirm_shift_"):
        shift_id = int(data.replace("confirm_shift_", ""))
        
        shift = await db.get_shift_by_id(shift_id)
        if not shift:
            await query.edit_message_text(
                f"{format_error('Ta zmiana już nie istnieje')}",
                parse_mode='HTML'
            )
            return
        
        confirmed_count = await db.get_shift_confirmed_count(shift_id)
        shift_limit = await db.get_shift_limit(shift_id)
        
        if shift_limit and confirmed_count >= shift_limit:
            await query.edit_message_text(
                f"{format_warning('Смена уже закрыта!')}\n\n"
                f"📍 <b>{shift['hotel']}</b>\n"
                f"📆 {shift['date']}\n"
                f"⏰ {shift['time_start']}-{shift['time_end']}\n\n"
                f"👥 <b>Уже набрано:</b> {confirmed_count} из {shift_limit} сотрудников\n\n"
                f"{format_info('Смена полностью укомплектована. Следующий раз будь быстрее! 💪')}",
                parse_mode='HTML'
            )
            return
        
        week_start = get_week_start_str()
        assigned_shifts = await db.get_assigned_shifts_for_week(week_start)
        already_confirmed = False
        for assigned in assigned_shifts:
            if assigned['user_id'] == user_id and assigned['date'] == shift['date'] and assigned['hotel'] == shift['hotel']:
                already_confirmed = True
                break
        
        if already_confirmed:
            await query.edit_message_text(
                f"{format_warning('Вы уже подтвердили эту смену!')}\n\n"
                f"📍 <b>{shift['hotel']}</b>\n"
                f"📆 {shift['date']}\n"
                f"⏰ {shift['time_start']}-{shift['time_end']}",
                parse_mode='HTML'
            )
            return
        
        user = await db.get_user(user_id)
        if user:
            user_name = f"{user['first_name']} {user['last_name'] or ''}".strip()
        else:
            user_name = "Неизвестно"
        
        try:
            date_obj = datetime.strptime(shift['date'], "%d.%m.%Y")
            day_name = date_obj.strftime("%A")
            days_pl = {
                'Monday': 'Poniedziałek',
                'Tuesday': 'Wtorek',
                'Wednesday': 'Środa',
                'Thursday': 'Czwartek',
                'Friday': 'Piątek',
                'Saturday': 'Sobota',
                'Sunday': 'Niedziela'
            }
            day_pl = days_pl.get(day_name, day_name)
        except:
            day_pl = shift['date']
        
        await db.assign_shift(
            user_id=user_id,
            day=day_pl,
            date=shift['date'],
            hotel=shift['hotel'],
            time_start=shift['time_start'],
            time_end=shift['time_end'],
            assigned_by=ADMIN_ID,
            week_start=week_start
        )
        
        await db.increment_shift_confirmed(shift_id)
        
        confirmed_count = await db.get_shift_confirmed_count(shift_id)
        shift_limit = await db.get_shift_limit(shift_id)
        
        is_full = bool(shift_limit) and confirmed_count >= shift_limit
        limit_text = str(shift_limit) if shift_limit else "∞"
        left_text = str(shift_limit - confirmed_count) if shift_limit else "∞"
        
        await query.edit_message_text(
            f"{format_success('Zmiana potwierdzona!')}\n\n"
            f"📍 <b>{shift['hotel']}</b>\n"
            f"📆 {shift['date']}\n"
            f"⏰ {shift['time_start']}-{shift['time_end']}\n\n"
            f"👥 <b>Подтверждено:</b> {confirmed_count} из {limit_text} сотрудников\n"
            f"{'🎉 <b>Смена полностью укомплектована!</b>' if is_full else 'ℹ️ <i>Осталось мест: ' + left_text + '</i>'}\n\n"
            f"{format_info('Dziękujemy! Udanej pracy 💪')}",
            parse_mode='HTML'
        )
        
        if is_full:
            await db.close_shift(shift_id)
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"✅ <b>НОВОЕ ПОДТВЕРЖДЕНИЕ!</b>\n"
                    "─────────────────────\n\n"
                    f"👤 <b>Сотрудник:</b> {user_name}\n"
                    f"📍 <b>Отель:</b> {shift['hotel']}\n"
                    f"📆 <b>Дата:</b> {shift['date']}\n"
                    f"⏰ <b>Время:</b> {shift['time_start']}-{shift['time_end']}\n\n"
                    f"👥 <b>Набрано:</b> {confirmed_count} из {shift_limit}\n"
                    f"🎉 <b>СМЕНА ЗАКРЫТА!</b>"
                ),
                parse_mode='HTML'
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"✅ <b>НОВОЕ ПОДТВЕРЖДЕНИЕ!</b>\n"
                    "─────────────────────\n\n"
                    f"👤 <b>Сотрудник:</b> {user_name}\n"
                    f"📍 <b>Отель:</b> {shift['hotel']}\n"
                    f"📆 <b>Дата:</b> {shift['date']}\n"
                    f"⏰ <b>Время:</b> {shift['time_start']}-{shift['time_end']}\n\n"
                    f"👥 <b>Набрано:</b> {confirmed_count} из {shift_limit}\n"
                    f"ℹ️ <i>Осталось мест: {shift_limit - confirmed_count}</i>"
                ),
                parse_mode='HTML'
            )
        
        return
    
    # ========== ОТКАЗ ОТ СМЕНЫ ==========
    if data.startswith("decline_shift_"):
        shift_id = int(data.replace("decline_shift_", ""))
        
        shift = await db.get_shift_by_id(shift_id)
        if not shift:
            await query.edit_message_text(
                f"{format_error('Ta zmiana już nie istnieje')}",
                parse_mode='HTML'
            )
            return
        
        if shift['status'] == 'confirmed':
            await query.edit_message_text(
                f"{format_warning('Ta zmiana została już potwierdzona')}",
                parse_mode='HTML'
            )
            return
        
        await db.decline_shift(shift_id)
        
        shift = await db.get_shift_by_id(shift_id)
        user = await db.get_user(shift['user_id'])
        if user:
            user_name = f"{user['first_name']} {user['last_name'] or ''}".strip()
        else:
            user_name = "Неизвестно"
        
        await query.edit_message_text(
            f"{format_error('Zmiana odrzucona')}\n\n"
            f"📍 <b>{shift['hotel']}</b>\n"
            f"📆 {shift['date']}\n"
            f"⏰ {shift['time_start']}-{shift['time_end']}",
            parse_mode='HTML'
        )
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"{format_header('Pracownik odrzucił zmianę', '❌')}"
                f"👤 <b>Pracownik:</b> {user_name}\n"
                f"📍 <b>Hotel:</b> {shift['hotel']}\n"
                f"📆 <b>Data:</b> {shift['date']}\n"
                f"⏰ <b>Godziny:</b> {shift['time_start']}-{shift['time_end']}\n\n"
                f"{format_error('Status: ODRZUCONA')}\n\n"
                f"{format_info('Znajdź innego pracownika')}"
            ),
            parse_mode='HTML'
        )
        return
    
    if data.startswith("select_emp_"):
        if not is_admin(user_id):
            await query.edit_message_text(
                f"{format_error('Доступ запрещен')}",
                parse_mode='HTML'
            )
            return
        
        emp_index = int(data.replace("select_emp_", ""))
        free_employees = temp_data.get(user_id, {}).get("free_employees", [])
        
        if emp_index >= len(free_employees):
            await query.edit_message_text(
                f"{format_error('Ошибка выбора сотрудника')}",
                parse_mode='HTML'
            )
            return
        
        selected_employee = free_employees[emp_index]
        found_day = temp_data.get(user_id, {}).get("found_day", "")
        time_start = temp_data.get(user_id, {}).get("time_start", "")
        time_end = temp_data.get(user_id, {}).get("time_end", "")
        
        temp_data[user_id]["selected_employee"] = selected_employee
        
        user_states[user_id] = "waiting_single_shift_data"
        
        await query.edit_message_text(
            f"{format_header('Введите данные смены', '📝')}"
            f"👤 <b>Сотрудник:</b> {selected_employee}\n"
            f"📅 <b>День:</b> {found_day}\n\n"
            f"{format_info('Введите название смены, дату и время:')}\n"
            f"<b>Примеры:</b>\n"
            f"<code>Sofitel Śniadania 19.08.2026(16:00-04:00)</code>\n"
            f"<code>Hilton Floor 21.08.2026(12:00-22:00)</code>\n"
            f"<code>Mercure 21.08.2026(8:00-16:00)</code>\n\n"
            f"{format_info('Или нажмите «Главное меню» для отмены')}",
            parse_mode='HTML',
            reply_markup=get_main_menu_inline()
        )
        return

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    username = update.effective_user.username
    
    if text == "/start" or text == "🏠 Главное меню":
        await start(update, context)
        return
    
    if text == "❓ Помощь":
        await help_command(update, context)
        return
    
    # ========== ОТПРАВИТЬ ГРАФИК ==========
    if text == "📝 Отправить график":
        if not is_schedule_submission_allowed():
            await update.message.reply_text(
                f"{format_error('Сейчас нельзя отправить график')}\n\n"
                f"{get_submission_window_text()}",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return

        _sch = await db.get_user_schedule(user_id, get_submit_week_start_str())
        has_schedule = _sch is not None and str(_sch).strip() != ""
        if has_schedule:
            await update.message.reply_text(
                f"{format_warning('Вы уже отправили график на эту неделю')}\n\n"
                f"📅 <b>{get_submit_week_range_text()}</b>\n\n"
                "⚠️ <b>На одну неделю — один раз.</b>\n"
                "✏️ Изменить можно через «✏️ Изменить график» (1 раз)",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        user_states[user_id] = "waiting_name"
        await update.message.reply_text(
            "📝 <b>Wprowadź swoje dane</b>\n"
            "─────────────────────\n\n"
            f"👤 <b>Wprowadź IMIĘ i NAZWISKO po angielsku:</b>\n"
            "<code>Ivan Ivanov</code>\n\n"
            f"📅 <i>Grafik na tydzień: {get_submit_week_range_text()}</i>\n\n"
            "⚠️ <b>График можно отправить только один раз на эту неделю!</b>",
            parse_mode='HTML',
            reply_markup=get_main_menu_inline()
        )
        return
    
    # ========== МОЙ ГРАФИК ==========
    if text == "📋 Мой график":
        week_start = get_week_start_str()
        # Смены от координатора (готовая рассылка)
        assigned = []
        if hasattr(db, 'get_assigned_shifts_for_user'):
            assigned = await db.get_assigned_shifts_for_user(user_id, week_start)
        else:
            all_a = await db.get_assigned_shifts_for_week(week_start)
            assigned = [a for a in all_a if a.get('user_id') == user_id]
        
        # Доп. смены (подтверждение лимита)
        extra_shifts = await db.get_user_shifts(user_id)
        # Что официант сам указал как доступность
        availability = await db.get_user_schedule(user_id)
        
        if not assigned and not extra_shifts and not availability:
            await update.message.reply_text(
                f"{format_header('Mój grafik', '📋')}"
                f"📅 <b>{get_week_range_text()}</b>\n\n"
                f"{format_info('Na ten tydzień nie ma jeszcze zmian')}\n\n"
                "💡 <i>Gdy kierownik wyśle grafik — pojawi się tutaj</i>",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        text_msg = f"{format_header('Mój grafik', '📋')}"
        text_msg += f"📅 <b>{get_week_range_text()}</b>\n"
        text_msg += "─" * 35 + "\n\n"
        
        # 1) Главное — смены, которые выдал координатор
        if assigned:
            text_msg += "📌 <b>Twoje zmiany (od kierownika):</b>\n\n"
            by_date = {}
            for s in assigned:
                by_date.setdefault(s.get('date') or '', []).append(s)
            for date in sorted(by_date.keys()):
                text_msg += f"📆 <b>{date}</b>\n"
                for s in by_date[date]:
                    hotel = s.get('hotel') or '—'
                    t0 = s.get('time_start') or ''
                    t1 = s.get('time_end') or ''
                    text_msg += f"📍 <b>{hotel}</b>\n"
                    text_msg += f"⏰ {t0}-{t1}\n"
                text_msg += "\n"
        else:
            text_msg += f"{format_info('Kierownik jeszcze nie przydzielił zmian na ten tydzień')}\n\n"
        
        # 2) Доп. смены (кнопка potwierdź)
        if extra_shifts:
            text_msg += "➕ <b>Dodatkowe zmiany:</b>\n"
            for s in extra_shifts:
                status_icon = "✅" if s.get('status') == 'confirmed' else "⏳"
                text_msg += f"{status_icon} <b>{s.get('hotel')}</b>\n"
                text_msg += f"   📆 {s.get('date')}  ⏰ {s.get('time_start')}-{s.get('time_end')}\n"
            text_msg += "\n"
        
        # 3) Опционально — что сам отправил (доступность)
        if availability and str(availability).strip():
            text_msg += "📝 <b>Twoja dostępność (wysłany grafik):</b>\n"
            text_msg += f"<i>{availability}</i>\n"
        
        await update.message.reply_text(
            text_msg,
            parse_mode='HTML',
            reply_markup=get_main_menu_inline()
        )
        return
    
    # ========== ИЗМЕНИТЬ ГРАФИК (СОТРУДНИК) ==========
    if text == "✏️ Изменить график":
        if not is_schedule_submission_allowed():
            await update.message.reply_text(
                f"{format_error('Сейчас нельзя изменить график')}\n\n"
                f"{get_submission_window_text()}",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return

        schedule = await db.get_user_schedule(user_id, get_submit_week_start_str())
        if not schedule:
            await update.message.reply_text(
                f"{format_error('Nie masz grafiku na nowy tydzień')}\n\n"
                f"📅 <b>{get_submit_week_range_text()}</b>\n\n"
                f"{format_info('Najpierw wyślij swój grafik')}\n"
                "💡 <i>Użyj przycisku «📝 Отправить график»</i>",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return

        edit_key = f"already_edited_{get_submit_week_start_str()}"
        if temp_data.get(user_id, {}).get(edit_key) or temp_data.get(user_id, {}).get("already_edited"):
            await update.message.reply_text(
                f"{format_warning('Вы уже изменили график')}\n\n"
                "⚠️ <b>График можно изменить только один раз!</b>\n\n"
                f"{format_info('Если нужно исправить ещё раз — обратитесь к администратору')}",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        user_states[user_id] = "waiting_edit_schedule"
        
        await update.message.reply_text(
            f"{format_header('Edytuj grafik', '✏️')}"
            f"📅 <b>{get_submit_week_range_text()}</b>\n"
            "───────────────────\n\n"
            f"{format_info('Twój obecny grafik:')}\n"
            f"{schedule}\n\n"
            f"{format_info('Wyślij NOWY grafik')}\n"
            "───────────────────\n\n"
            "⚠️ <b>График можно изменить только один раз!</b>\n\n"
            f"{format_info('Wpisz swój grafik według wzoru:')}\n\n"
            "<code>Poniedziałek:</code>\n"
            "<code>Wtorek:</code>\n"
            "<code>Środa:</code>\n"
            "<code>Czwartek:</code>\n"
            "<code>Piątek:</code>\n"
            "<code>Sobota:</code>\n"
            "<code>Niedziela:</code>\n\n"
            "───────────────────\n"
            f"{format_info('Przykład wypełnienia:')}\n\n"
            "<code>Poniedziałek: cały dzień</code>\n"
            "<code>Wtorek: od 10:00</code>\n"
            "<code>Środa: do 16:00</code>\n"
            "<code>Czwartek: od 9:00 do 18:00</code>\n"
            "<code>Piątek: nie mogę</code>\n"
            "<code>Sobota: wolne</code>\n"
            "<code>Niedziela: po południu</code>\n\n"
            "───────────────────\n"
            f"{format_info('Pamiętaj - podaj dzień tygodnia!')}",
            parse_mode='HTML',
            reply_markup=get_main_menu_inline()
        )
        return
    
    # ========== ВВОД ИМЕНИ ==========
    if user_states.get(user_id) == "waiting_name":
        if not is_schedule_submission_allowed():
            user_states[user_id] = None
            temp_data.pop(user_id, None)
            await update.message.reply_text(
                f"{format_error('Время приёма графиков закончилось')}\n\n"
                f"{get_submission_window_text()}",
                parse_mode='HTML',
                reply_markup=get_main_reply_keyboard()
            )
            return

        if not re.match(r'^[A-Za-z\s\-]+$', text.strip()):
            await update.message.reply_text(
                f"{format_error('Błędny format')}\n\n"
                f"{format_info('Imię i nazwisko muszą być po angielsku')}\n"
                "<b>Przykład:</b> <code>Ivan Ivanov</code>\n\n"
                "💡 <i>Tylko litery alfabetu łacińskiego</i>",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        if len(text.strip()) < 3:
            await update.message.reply_text(
                f"{format_error('Za krótkie imię')}\n\n"
                f"{format_info('Wprowadź IMIĘ i NAZWISKO po angielsku')}\n"
                "<b>Przykład:</b> <code>Ivan Ivanov</code>",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        temp_data[user_id] = {"full_name": text.strip()}
        
        name_parts = text.strip().split()
        first_name = name_parts[0] if len(name_parts) > 0 else text.strip()
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ''
        
        await db.update_user_name(user_id, first_name, last_name)
        if username:
            await db.update_username(user_id, username)
        
        user_states[user_id] = "waiting_schedule"
        
        await update.message.reply_text(
            f"✅ <b>Imię zapisane:</b> {text.strip()}\n\n"
            f"{format_header('Napisz swój grafik', '📝')}"
            f"📅 <b>{get_submit_week_range_text()}</b>\n"
            "─────────────────────\n\n"
            f"{format_info('Wpisz swój grafik według wzoru:')}\n\n"
            "<code>Poniedziałek:</code>\n"
            "<code>Wtorek:</code>\n"
            "<code>Środa:</code>\n"
            "<code>Czwartek:</code>\n"
            "<code>Piątek:</code>\n"
            "<code>Sobota:</code>\n"
            "<code>Niedziela:</code>\n\n"
            "─────────────────────\n"
            f"{format_info('Przykład wypełnienia:')}\n\n"
            "<code>Poniedziałek: cały dzień</code>\n"
            "<code>Wtorek: od 10:00</code>\n"
            "<code>Środa: do 16:00</code>\n"
            "<code>Czwartek: od 9:00 do 18:00</code>\n"
            "<code>Piątek: nie mogę</code>\n"
            "<code>Sobota: wolne</code>\n"
            "<code>Niedziela: po południu</code>\n\n"
            "─────────────────────\n"
            f"{format_info('Pamiętaj - podaj dzień tygodnia!')}",
            parse_mode='HTML',
            reply_markup=get_main_menu_inline()
        )
        return
    
    # ========== СОХРАНЕНИЕ ГРАФИКА ==========
    if user_states.get(user_id) == "waiting_schedule":
        if not is_schedule_submission_allowed():
            user_states[user_id] = None
            temp_data.pop(user_id, None)
            await update.message.reply_text(
                f"{format_error('Время приёма графиков закончилось')}\n\n"
                f"{get_submission_window_text()}",
                parse_mode='HTML',
                reply_markup=get_main_reply_keyboard()
            )
            return

        if len(text.strip()) < 3:
            await update.message.reply_text(
                f"{format_error('Grafik jest za krótki')}\n\n"
                f"{format_info('Podaj przynajmniej jeden dzień')}\n"
                "<b>Przykład:</b> <code>Poniedziałek: 08:00-16:00</code>",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        full_name = temp_data.get(user_id, {}).get('full_name', 'Неизвестно')
        # пт/сб — график на СЛЕДУЮЩУЮ неделю; таблицы в пн–вс смотрят ТЕКУЩУЮ
        week_start = get_submit_week_start_str()
        
        await db.save_user_schedule(user_id, text, week_start)
        if username:
            await db.update_username(user_id, username)
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"{format_header('Новый график', '📋')}"
                f"👤 <b>Сотрудник:</b> {full_name}\n"
                f"📱 @{username or 'нет username'}\n"
                f"📅 <b>{get_submit_week_range_text()}</b>\n\n"
                f"{text}"
            ),
            parse_mode='HTML'
        )
        
        user_states[user_id] = None
        temp_data.pop(user_id, None)
        
        await update.message.reply_text(
            f"{format_success('Grafik wysłany!')}\n\n"
            f"📅 <b>{get_submit_week_range_text()}</b>\n\n"
            f"{format_info('Dane dodane do tabeli Excel')}\n"
            f"{format_info('Oczekuj na gotowy grafik od menedżera')}\n\n"
            "⚠️ <b>Отправить можно только один раз. Изменить — тоже только один раз.</b>",
            parse_mode='HTML',
            reply_markup=get_main_reply_keyboard()
        )
        return
    
    # ========== РЕДАКТИРОВАНИЕ ГРАФИКА (СОТРУДНИК) ==========
    if user_states.get(user_id) == "waiting_edit_schedule":
        if not is_schedule_submission_allowed():
            user_states[user_id] = None
            await update.message.reply_text(
                f"{format_error('Время приёма графиков закончилось')}\n\n"
                f"{get_submission_window_text()}",
                parse_mode='HTML',
                reply_markup=get_main_reply_keyboard()
            )
            return

        if len(text.strip()) < 3:
            await update.message.reply_text(
                f"{format_error('Grafik jest za krótki')}\n\n"
                f"{format_info('Podaj przynajmniej jeden dzień')}",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        full_name = temp_data.get(user_id, {}).get('full_name', 'Неизвестно')
        week_start = get_submit_week_start_str()
        
        await db.update_user_schedule(user_id, text, week_start)
        if username:
            await db.update_username(user_id, username)
        
        # Помечаем, что график уже был изменён (один раз)
        if user_id not in temp_data:
            temp_data[user_id] = {}
        temp_data[user_id][f"already_edited_{week_start}"] = True
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "✏️ <b>ГРАФИК ИЗМЕНЕН</b>\n"
                "─────────────────────\n\n"
                f"👤 <b>Сотрудник:</b> {full_name}\n"
                f"📱 @{username or 'нет username'}\n"
                f"📅 <b>{get_submit_week_range_text()}</b>\n\n"
                f"📋 <b>Новый график:</b>\n"
                f"{text}\n\n"
                "🔄 <i>Старый график удален</i>\n"
                "✅ <i>Новый график сохранен</i>\n"
                "⚠️ <i>Это было единственное разрешённое изменение</i>"
            ),
            parse_mode='HTML'
        )
        
        user_states[user_id] = None
        
        await update.message.reply_text(
            "✅ <b>ГРАФИК ИЗМЕНЕН!</b>\n\n"
            f"📅 <b>{get_submit_week_range_text()}</b>\n\n"
            f"📋 <b>Новый график:</b>\n"
            f"{text}\n\n"
            "ℹ️ <b>Уведомление отправлено менеджеру</b>\n"
            "ℹ️ <b>Таблица Excel обновлена</b>\n\n"
            "⚠️ <b>График можно изменить только один раз!</b>",
            parse_mode='HTML',
            reply_markup=get_main_reply_keyboard()
        )
        return
    
    # ========== АДМИНСКИЕ ФУНКЦИИ ==========
    if not is_admin(user_id):
        await update.message.reply_text(
            f"{format_error('Доступ запрещен')}",
            parse_mode='HTML'
        )
        return
    
    # ========== ВСЕ ГРАФИКИ ==========
    if text == "📊 Все графики":
        week_start = get_week_start_str()
        schedules = await db.get_all_schedules_with_users(week_start)
        if not schedules and hasattr(db, 'get_latest_schedule_week'):
            latest = await db.get_latest_schedule_week()
            if latest and latest != week_start:
                week_start = latest
                schedules = await db.get_all_schedules_with_users(week_start)
        if not schedules:
            await update.message.reply_text(
                f"{format_header('Все графики', '📊')}"
                f"{format_info('Нет отправленных графиков')}\n\n"
                f"📅 <i>{get_week_range_text()}</i>",
                parse_mode='HTML',
                reply_markup=get_admin_reply_keyboard()
            )
            return

        week_range = get_week_range_from_str(week_start)
        names = "\n".join(f"• {s.get('full_name') or s.get('user_id')}" for s in schedules)
        await update.message.reply_text(
            f"{format_header('Все графики', '📊')}"
            f"📅 <b>{week_range}</b>\n"
            f"👥 {len(schedules)}\n\n{names}\n\n"
            f"{format_info('Полный текст — в Excel-отчете')}",
            parse_mode='HTML',
            reply_markup=get_admin_reply_keyboard()
        )
        return

    # ========== СЛЕДУЮЩАЯ НЕДЕЛЯ (новые графики пт–сб) ==========
    if text == "📅 След. неделя":
        next_week = get_submit_week_start_str()
        next_range = get_week_range_from_str(next_week)
        schedules = await db.get_all_schedules_with_users(next_week)
        if not schedules:
            await update.message.reply_text(
                f"{format_header('Следующая неделя', '📅')}"
                f"📅 <b>{next_range}</b>\n\n"
                f"{format_info('Пока нет новых графиков на следующую неделю')}\n"
                "💡 <i>Официанты присылают их в пятницу и субботу</i>",
                parse_mode='HTML',
                reply_markup=get_admin_reply_keyboard()
            )
            return

        await update.message.reply_text(
            f"{format_header('Следующая неделя', '📅')}"
            f"📅 <b>{next_range}</b>\n"
            f"👥 Прислали график: <b>{len(schedules)}</b>\n\n"
            + "\n".join(
                f"• {s.get('full_name') or s.get('user_id')}"
                for s in schedules
            ),
            parse_mode='HTML',
            reply_markup=get_admin_reply_keyboard()
        )
        try:
            ensure_excel_path(next_week)
            excel_path = excel_exporter.export_schedules_to_excel(schedules, next_week)
            path = excel_path or getattr(excel_exporter, 'file_path', None)
            if path and os.path.isfile(path):
                with open(path, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=user_id,
                        document=f,
                        filename=f"Grafik_{next_week}.xlsx",
                        caption=f"📁 Следующая неделя (главная таблица): {next_range}\n👥 {len(schedules)} человек",
                        parse_mode='HTML'
                    )
            else:
                await update.message.reply_text(
                    f"{format_warning('Excel не создался, но графики в базе есть')}: {len(schedules)}",
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Excel след. неделя: {e}")
            await update.message.reply_text(
                f"{format_error('Ошибка Excel')}\n{e}",
                parse_mode='HTML'
            )

        # Вторая таблица: неназначенные на СЛЕДУЮЩУЮ неделю
        try:
            assigned_shifts = await db.get_assigned_shifts_for_week(next_week)
            assigned_dates_by_user = {}
            for shift in assigned_shifts:
                uid = shift['user_id']
                date = shift['date']
                assigned_dates_by_user.setdefault(uid, [])
                if date not in assigned_dates_by_user[uid]:
                    assigned_dates_by_user[uid].append(date)

            days_order = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
            week_start_date = datetime.strptime(next_week, "%Y-%m-%d").date()
            day_dates = {day: (week_start_date + timedelta(days=i)).strftime("%d.%m.%Y")
                         for i, day in enumerate(days_order)}

            not_assigned = []
            for user in schedules:
                schedule_text = (user.get('schedule_text') or '').strip()
                if not schedule_text:
                    continue
                employee_days = []
                for line in schedule_text.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    found_day = None
                    for day in days_order:
                        if day.lower() in line.lower():
                            found_day = day
                            break
                    if not found_day:
                        continue
                    time_info = line.split(':', 1)[1].strip() if ':' in line else ''
                    tl = time_info.lower()
                    if any(w in tl for w in ['wolne', 'nie mogę', 'off', 'free', 'wolny']):
                        continue
                    if not time_info:
                        time_info = 'cały dzień'
                    date_str = day_dates.get(found_day)
                    if date_str:
                        employee_days.append({'day': found_day, 'date': date_str, 'time': time_info})
                if not employee_days:
                    continue
                assigned_dates = assigned_dates_by_user.get(user['user_id'], [])
                missing = [d for d in employee_days if d['date'] not in assigned_dates]
                if missing or not assigned_dates:
                    not_assigned.append({
                        'full_name': user.get('full_name'),
                        'username': user.get('username'),
                        'missing_dates': missing if missing else employee_days,
                        'employee_days': employee_days,
                    })

            if not_assigned:
                base_path = ensure_excel_path(next_week)
                na_path = not_assigned_exporter.export_not_assigned_to_excel(
                    not_assigned, next_week, base_path
                )
                with open(na_path, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=user_id,
                        document=f,
                        filename=f"Не_назначенные_{next_week}.xlsx",
                        caption=(
                            f"📁 <b>Не назначенные (следующая неделя)</b>\n"
                            f"📅 {next_range}\n"
                            f"👥 {len(not_assigned)} человек"
                        ),
                        parse_mode='HTML'
                    )
            else:
                await update.message.reply_text(
                    f"{format_success('На следующую неделю все дни уже назначены (или нечего назначать)')}\n"
                    f"📅 {next_range}",
                    parse_mode='HTML',
                    reply_markup=get_admin_reply_keyboard()
                )
        except Exception as e:
            logger.error(f"Не назначенные след. неделя: {e}")
            await update.message.reply_text(
                f"{format_error('Ошибка таблицы неназначенных')}\n{e}",
                parse_mode='HTML'
            )
        return
    
    # ========== EXCEL-ОТЧЕТ ==========
    if text == "📁 Excel-отчет":
        week_start = get_week_start_str()
        schedules = await db.get_all_schedules_with_users(week_start)
        if not schedules and hasattr(db, 'get_latest_schedule_week'):
            latest = await db.get_latest_schedule_week()
            if latest:
                week_start = latest
                schedules = await db.get_all_schedules_with_users(week_start)
        
        if not schedules:
            await update.message.reply_text(
                f"{format_header('Excel-отчет', '📁')}"
                f"{format_info('Нет данных для экспорта')}\n\n"
                f"📅 <i>{get_week_range_text()}</i>\n\n"
                "💡 <i>Сотрудники ещё не отправили графики</i>",
                parse_mode='HTML',
                reply_markup=get_admin_reply_keyboard()
            )
            return
        
        ensure_excel_path(week_start)
        excel_path = excel_exporter.export_schedules_to_excel(schedules, week_start)
        
        try:
            with open(excel_path, 'rb') as f:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    filename=f"Графики_{week_start}.xlsx",
                    caption=(
                        f"{format_header('Excel-отчет', '📁')}"
                        f"📅 <b>{get_week_range_text()}</b>\n"
                        f"👥 Всего: <b>{len(schedules)}</b> сотрудников\n\n"
                        "📋 <i>Графики собраны в одной таблице</i>"
                    ),
                    parse_mode='HTML'
                )
            await update.message.reply_text(
                f"{format_success('Excel-отчет отправлен')}\n📅 {get_week_range_text()}",
                parse_mode='HTML',
                reply_markup=get_admin_reply_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка отправки Excel: {e}")
            await update.message.reply_text(
                f"{format_error('Ошибка отправки файла')}\n\n{str(e)}",
                parse_mode='HTML',
                reply_markup=get_admin_reply_keyboard()
            )
        return
    
    # ========== НЕ НАЗНАЧЕННЫЕ ==========
    if text == "📋 Не назначенные":
        if not is_admin(user_id):
            await update.message.reply_text(
                f"{format_error('Доступ запрещен')}",
                parse_mode='HTML'
            )
            return
        
        # Главная «Не назначенные» = ТЕКУЩАЯ неделя (с понедельника сюда перетекают графики)
        week_start = get_week_start_str()
        week_range = get_week_range_from_str(week_start)
        schedules = await db.get_all_schedules_with_users(week_start)
        assigned_shifts = await db.get_assigned_shifts_for_week(week_start)
        
        assigned_dates_by_user = {}
        assigned_days_by_user = {}
        for shift in assigned_shifts:
            user_id_db = shift['user_id']
            date = normalize_date(shift.get('date'))
            day_name = (shift.get('day') or '').strip()
            assigned_dates_by_user.setdefault(user_id_db, [])
            assigned_days_by_user.setdefault(user_id_db, [])
            if date and date not in assigned_dates_by_user[user_id_db]:
                assigned_dates_by_user[user_id_db].append(date)
            if day_name and day_name not in assigned_days_by_user[user_id_db]:
                assigned_days_by_user[user_id_db].append(day_name)
        
        not_assigned = []
        days_order = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
        
        week_start_date = datetime.strptime(week_start, "%Y-%m-%d").date()
        day_dates = {}
        for i, day in enumerate(days_order):
            date_obj = week_start_date + timedelta(days=i)
            day_dates[day] = date_obj.strftime("%d.%m.%Y")
        
        for user in schedules:
            if not user.get('schedule_text'):
                continue
            
            user_id_db = user['user_id']
            full_name = user['full_name']
            username = user.get('username')
            schedule_text = user['schedule_text']
            
            employee_days = []
            lines = schedule_text.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                found_day = None
                for day in days_order:
                    if day.lower() in line.lower():
                        found_day = day
                        break
                
                if not found_day:
                    continue
                
                time_info = ""
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) > 1:
                        time_info = parts[1].strip()
                else:
                    for day in days_order:
                        if day.lower() in line.lower():
                            time_info = line.replace(day, '').strip()
                            break
                
                time_lower = time_info.lower()
                if any(word in time_lower for word in ['wolne', 'nie mogę', 'off', 'free', 'wolny']):
                    continue
                
                if not time_info:
                    time_info = "cały dzień"
                
                date_str = day_dates.get(found_day)
                if date_str:
                    employee_days.append({
                        'day': found_day,
                        'date': date_str,
                        'time': time_info
                    })
            
            if not employee_days:
                continue
            
            assigned_dates = [normalize_date(d) for d in assigned_dates_by_user.get(user_id_db, [])]
            assigned_days = assigned_days_by_user.get(user_id_db, [])
            missing_dates = []
            
            for emp_day in employee_days:
                date_ok = normalize_date(emp_day['date']) in assigned_dates
                day_ok = emp_day['day'] in assigned_days
                if not date_ok and not day_ok:
                    missing_dates.append({
                        'day': emp_day['day'],
                        'date': emp_day['date'],
                        'time': emp_day['time']
                    })
            
            if missing_dates:
                not_assigned.append({
                    'full_name': full_name,
                    'username': username,
                    'missing_dates': missing_dates,
                    'employee_days': employee_days
                })
        
        if not_assigned:
            try:
                base_path = ensure_excel_path(week_start)
                excel_path = not_assigned_exporter.export_not_assigned_to_excel(
                    not_assigned, 
                    week_start, 
                    base_path
                )
                with open(excel_path, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=user_id,
                        document=f,
                        filename=f"Не_назначенные_{week_start}.xlsx",
                        caption=(
                            f"📁 <b>Сотрудники без назначений</b>\n"
                            f"📅 {week_range}\n"
                            f"👥 {len(not_assigned)} человек\n\n"
                            f"ℹ️ <i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
                        ),
                        parse_mode='HTML'
                    )
                    await update.message.reply_text(
                        f"{format_success('Таблица обновлена!')}\n"
                        f"📅 {week_range}\n"
                        f"👥 {len(not_assigned)} человек без назначений",
                        parse_mode='HTML',
                        reply_markup=get_admin_reply_keyboard()
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки Excel: {e}")
                import traceback
                traceback.print_exc()
                await update.message.reply_text(
                    f"{format_error('Ошибка создания таблицы')}\n\n{str(e)}",
                    parse_mode='HTML',
                    reply_markup=get_admin_reply_keyboard()
                )
        else:
            await update.message.reply_text(
                f"{format_success('Все сотрудники полностью назначены на все свои дни!')}\n"
                f"📅 {week_range}",
                parse_mode='HTML',
                reply_markup=get_admin_reply_keyboard()
            )
        
        return
    
    # ========== РЕДАКТИРОВАТЬ ГОТОВЫЙ ГРАФИК ==========
    if text == "✏️ Редактировать график":
        if not is_admin(user_id):
            await update.message.reply_text(
                f"{format_error('Доступ запрещен')}",
                parse_mode='HTML'
            )
            return
        
        week_start = get_week_start_str()
        assigned_shifts = await db.get_assigned_shifts_for_week(week_start)
        
        if not assigned_shifts:
            await update.message.reply_text(
                f"{format_warning('Нет отправленных графиков для редактирования')}\n\n"
                f"{format_info('Сначала отправьте график через «📤 Рассылка»')}",
                parse_mode='HTML',
                reply_markup=get_admin_reply_keyboard()
            )
            return
        
        current_schedule = "📋 <b>ТЕКУЩИЙ ГРАФИК</b>\n"
        current_schedule += "─────────────────────\n\n"
        
        shifts_by_date = {}
        for shift in assigned_shifts:
            date = shift['date']
            if date not in shifts_by_date:
                shifts_by_date[date] = []
            shifts_by_date[date].append(shift)
        
        for date in sorted(shifts_by_date.keys()):
            current_schedule += f"📆 <b>{date}</b>\n"
            for shift in shifts_by_date[date]:
                user = await db.get_user(shift['user_id'])
                if user:
                    user_name = f"{user['first_name']} {user['last_name'] or ''}".strip()
                else:
                    user_name = "Неизвестно"
                current_schedule += f"   🏨 {shift['hotel']} ({shift['time_start']}-{shift['time_end']}) - {user_name}\n"
            current_schedule += "\n"
        
        if user_id not in temp_data:
            temp_data[user_id] = {}
        temp_data[user_id]["edit_week_start"] = week_start
        
        user_states[user_id] = "waiting_edit_final_schedule"
        
        await update.message.reply_text(
            f"{current_schedule}\n"
            f"{format_info('Введите НОВЫЙ график в формате:')}\n"
            "<code>Hotel: President\n"
            "20.08.2026\n"
            "08:00-12:00\n"
            "Anton Rozehan\n\n"
            "21.08.2026\n"
            "08:00-12:00\n"
            "Anton Rozehan\n"
            "Alex\n\n"
            "22.08.2026\n"
            "08:00-12:00\n"
            "Anton Rozehan\n"
            "Alex</code>\n\n"
            f"{format_info('Или нажмите «Главное меню» для отмены')}",
            parse_mode='HTML',
            reply_markup=get_main_menu_inline()
        )
        return
    
    # ========== СВОБОДНЫЕ ==========
    if text == "🔍 Свободные":
        user_states[user_id] = "waiting_find_employees"
        await update.message.reply_text(
            f"{format_header('Szukaj wolnych', '🔍')}"
            f"{format_info('Podaj dzień tygodnia po polsku:')}\n\n"
            "<b>Przykłady:</b>\n"
            "<code>Piątek</code> lub <code>Piatek</code>\n\n"
            f"{format_info('Lub naciśnij «Главное меню» aby anulować')}",
            parse_mode='HTML',
            reply_markup=get_main_menu_inline()
        )
        return
    
    # ========== СТАТИСТИКА ==========
    if text == "📈 Статистика":
        schedules = await db.get_all_schedules_with_users()
        all_users = await db.get_all_users_with_names()
        
        total = len(all_users)
        submitted = len(schedules)
        not_submitted = total - submitted
        submitted_percent = round(submitted/total*100) if total > 0 else 0
        
        text_msg = (
            f"{format_header('Статистика', '📈')}"
            f"👥 <b>Всего сотрудников:</b> {total}\n"
            f"✅ <b>Отправили график:</b> {submitted} ({submitted_percent}%)\n"
            f"❌ <b>Не отправили:</b> {not_submitted}\n\n"
        )
        
        if not_submitted > 0:
            text_msg += f"{format_info('Кто не отправил:')}\n"
            submitted_names = [s['full_name'] for s in schedules]
            for u in all_users:
                if u['full_name'] not in submitted_names:
                    text_msg += f"• {u['full_name']}\n"
        
        await update.message.reply_text(
            text_msg,
            parse_mode='HTML',
            reply_markup=get_admin_reply_keyboard()
        )
        return
    
    # ========== ОЧИСТКА ГРАФИКОВ (НЕДЕЛЯ → ДА/НЕТ) ==========
    if text == "🧹 Очистить графики":
        if not is_admin(user_id):
            await update.message.reply_text(
                f"{format_error('Доступ запрещен')}",
                parse_mode='HTML'
            )
            return
        user_states[user_id] = "waiting_clear_week"
        await update.message.reply_text(
            f"{format_header('Очистка недели', '🧹')}"
            "Введите неделю, которую нужно очистить.\n\n"
            "<b>Примеры:</b>\n"
            "<code>17.08-23.08</code>\n"
            "<code>17.08.2026 - 23.08.2026</code>\n\n"
            f"{format_info('Другие недели не будут затронуты')}",
            parse_mode='HTML',
            reply_markup=get_main_menu_inline()
        )
        return

    if user_states.get(user_id) == "waiting_clear_week":
        if not is_admin(user_id):
            return
        parsed = parse_week_range_input(text)
        if not parsed:
            await update.message.reply_text(
                f"{format_error('Не понял неделю')}\n\n"
                "Пример: <code>17.08-23.08</code>",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        week_start, week_range = parsed
        temp_data[user_id] = temp_data.get(user_id, {})
        temp_data[user_id]["clear_week_start"] = week_start
        temp_data[user_id]["clear_week_range"] = week_range
        user_states[user_id] = None
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да, очистить", callback_data="confirm_clear_schedules"),
                InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_clear_schedules")
            ]
        ])
        await update.message.reply_text(
            f"{format_header('Подтверждение очистки', '🧹')}"
            f"📅 Неделя: <b>{week_range}</b>\n\n"
            "Будет удалено ТОЛЬКО за эту неделю:\n"
            "• графики официантов\n"
            "• назначенные смены\n"
            "• доп. смены на эти даты\n\n"
            "Другие недели не трогаем.\n"
            "❗️ <b>Отменить после Да нельзя</b>",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return
    
    # ========== РАССЫЛКА ГОТОВОГО ГРАФИКА ==========
    if text == "📤 Рассылка":
        user_states[user_id] = "waiting_final_schedule"
        from config import WEEKDAYS_PL
        
        days_example = ", ".join(WEEKDAYS_PL[:3]) + ", ..."
        
        await update.message.reply_text(
            f"{format_header('Рассылка графика', '📤')}"
            f"📅 <b>{get_week_range_from_str(get_broadcast_week_start_str())}</b>\n"
            f"ℹ️ <i>Пт–вс рассылка пишется на СЛЕДУЮЩУЮ неделю</i>\n\n"
            f"{format_info('Поддерживаемые форматы:')}\n\n"
            "<b>Формат 1:</b>\n"
            "<code>Hotel 20.08.2026(08:00-16:00) - Ivan Ivanov</code>\n\n"
            "<b>Формат 2:</b>\n"
            "<code>Hotel: Novotel Śniadania\n"
            "22.08.2026\n"
            "06:00-12:00\n"
            "Polina Tkach\n"
            "Viktoriia Kulik</code>\n\n"
            f"{format_info('Текст под графиком (для всех):')}\n"
            "После графика добавьте строку <code>---</code> и текст:\n"
            "<code>---\n"
            "Novotel Centrum:\n"
            "Адрес: Marszałkowska 94/98\n"
            "Форма: белая рубашка, черные штаны...\n"
            "Приходите за 10 мин до смены</code>\n\n"
            f"{format_info('Или нажмите «Главное меню» для отмены')}",
            parse_mode='HTML',
            reply_markup=get_main_menu_inline()
        )
        return
    
    # ========== ВВОД ЛИМИТА ДЛЯ СМЕНЫ ==========
    if user_states.get(user_id) == "waiting_broadcast_shift_limit":
        if not is_admin(user_id):
            return
        
        try:
            limit = int(text.strip())
            if limit < 1:
                await update.message.reply_text(
                    f"{format_error('Количество должно быть больше 0')}\n\n"
                    f"{format_info('Введите число больше 0:')}",
                    parse_mode='HTML',
                    reply_markup=get_main_menu_inline()
                )
                return
            if limit > 20:
                await update.message.reply_text(
                    f"{format_warning('Слишком большое количество')}\n\n"
                    f"{format_info('Максимум 20 сотрудников')}\n"
                    f"{format_info('Введите число от 1 до 20:')}",
                    parse_mode='HTML',
                    reply_markup=get_main_menu_inline()
                )
                return
        except ValueError:
            await update.message.reply_text(
                f"{format_error('Введите число!')}\n\n"
                f"{format_info('Пример: <code>3</code>')}",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        found_day = temp_data.get(user_id, {}).get("broadcast_day", "")
        found_date = temp_data.get(user_id, {}).get("broadcast_date", "")
        
        temp_data[user_id]["shift_limit"] = limit
        
        user_states[user_id] = "waiting_broadcast_shift_data"
        
        await update.message.reply_text(
            f"{format_success('Лимит установлен: ' + str(limit) + ' сотрудников')}\n\n"
            f"{format_header('Wprowadź dane zmiany', '📝')}"
            f"📅 <b>Dzień:</b> {found_day} ({found_date})\n"
            f"👥 <b>Лимит:</b> {limit} сотрудников\n\n"
            f"{format_info('Введите название смены, дату и время:')}\n"
            f"<b>Примеры:</b>\n"
            f"<code>Sofitel Śniadania 19.08.2026(16:00-04:00)</code>\n"
            f"<code>Hilton Floor 21.08.2026(12:00-22:00)</code>\n"
            f"<code>Mercure 21.08.2026(8:00-16:00)</code>\n"
            f"<code>Novotel centrum 22.08.2026(10:00-18:00)</code>\n\n"
            f"{format_info('Или нажмите «Главное меню» для отмены')}",
            parse_mode='HTML',
            reply_markup=get_main_menu_inline()
        )
        return
    
    # ========== ПОИСК СВОБОДНЫХ (ВВОД) ==========
    if user_states.get(user_id) == "waiting_find_employees":
        if not is_admin(user_id):
            return
        
        input_text = text.strip()
        
        days_map = {
            'poniedziałek': 'Poniedziałek', 'pon': 'Poniedziałek',
            'wtorek': 'Wtorek', 'wt': 'Wtorek',
            'środa': 'Środa', 'śr': 'Środa', 'sroda': 'Środa', 'sr': 'Środa',
            'czwartek': 'Czwartek', 'czw': 'Czwartek',
            'piątek': 'Piątek', 'pt': 'Piątek', 'piatek': 'Piątek',
            'sobota': 'Sobota', 'sob': 'Sobota',
            'niedziela': 'Niedziela', 'nd': 'Niedziela'
        }
        
        found_day = None
        input_lower = input_text.lower()
        
        for key, value in days_map.items():
            if key in input_lower:
                found_day = value
                break
        
        if not found_day:
            await update.message.reply_text(
                f"{format_error('Nie udało się określić dnia')}\n\n"
                f"{format_info('Podaj dzień tygodnia po polsku:')}\n"
                "<b>Przykład:</b> <code>Piątek</code> lub <code>Piatek</code>",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        week_start = get_week_start_str()
        week_start_date = datetime.strptime(week_start, "%Y-%m-%d").date()
        days_order = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
        
        found_date = None
        for i, day in enumerate(days_order):
            if day == found_day:
                date_obj = week_start_date + timedelta(days=i)
                found_date = date_obj.strftime("%d.%m.%Y")
                break
        
        assigned_shifts = await db.get_assigned_shifts_for_week(week_start)
        assigned_users_on_date = []
        for shift in assigned_shifts:
            if shift['date'] == found_date:
                assigned_users_on_date.append(shift['user_id'])
        
        all_users_with_schedules = await db.get_all_users_with_schedules()
        
        free_employees = []
        available_employees = []
        all_employees = []
        
        for user in all_users_with_schedules:
            user_id_db = user['user_id']
            full_name = user['full_name']
            username = user['username']
            schedule_text = user['schedule_text']
            
            if not schedule_text:
                continue
            
            day_found = False
            time_info = ""
            is_free = False
            
            lines = schedule_text.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if found_day.lower() in line.lower():
                    day_found = True
                    
                    if ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) > 1:
                            time_info = parts[1].strip()
                    else:
                        for d in days_order:
                            if d.lower() in line.lower():
                                time_info = line.replace(d, '').strip()
                                break
                    
                    time_lower = time_info.lower()
                    if any(word in time_lower for word in ['wolne', 'nie mogę', 'off', 'free', 'wolny']):
                        is_free = True
                    break
            
            if not day_found:
                continue
            
            is_assigned = user_id_db in assigned_users_on_date
            
            if is_free:
                free_employees.append({
                    'full_name': full_name,
                    'username': username,
                    'time': 'Wolny'
                })
                all_employees.append({
                    'full_name': full_name,
                    'username': username,
                    'time': 'Wolny',
                    'is_free': True,
                    'user_id': user_id_db,
                    'is_assigned': is_assigned
                })
            else:
                time_from = ""
                time_to = ""
                
                if time_info:
                    od_match = re.search(r'od\s*(\d{1,2}:\d{2})', time_info, re.IGNORECASE)
                    if od_match:
                        time_from = od_match.group(1)
                    
                    do_match = re.search(r'do\s*(\d{1,2}:\d{2})', time_info, re.IGNORECASE)
                    if do_match:
                        time_to = do_match.group(1)
                    
                    if not time_from and not time_to:
                        if 'cały dzień' in time_info.lower() or 'caly dzien' in time_info.lower():
                            time_from = "od rana"
                            time_to = "do wieczora"
                        elif time_info and time_info not in ['wolne', 'nie mogę', 'off', 'free', 'wolny']:
                            time_from = time_info
                
                if time_from and time_to:
                    time_display = f"od {time_from} do {time_to}"
                elif time_from:
                    time_display = f"od {time_from}"
                elif time_to:
                    time_display = f"do {time_to}"
                else:
                    time_display = "cały dzień"
                
                employee_data = {
                    'full_name': full_name,
                    'username': username,
                    'time': time_display,
                    'time_from': time_from,
                    'time_to': time_to,
                    'is_free': False,
                    'user_id': user_id_db,
                    'is_assigned': is_assigned
                }
                
                all_employees.append(employee_data)
                
                if not is_assigned:
                    available_employees.append(employee_data)
        
        result_text = f"{format_header('Сотрудники на день', '🔍')}"
        result_text += f"📅 <b>День:</b> {found_day} ({found_date})\n"
        result_text += "─" * 35 + "\n\n"
        
        if all_employees:
            result_text += f"📋 <b>Все сотрудники, указавшие {found_day}:</b> {len(all_employees)}\n\n"
            for i, emp in enumerate(all_employees, 1):
                status_icon = "❌" if emp.get('is_free', False) else "🟢"
                assigned_icon = "✅" if emp.get('is_assigned', False) else "⏳"
                result_text += f"{i}. <b>{emp['full_name']}</b>\n"
                if emp['username']:
                    result_text += f"   📱 @{emp['username']}\n"
                result_text += f"   ⏰ {emp['time']}\n"
                if emp.get('is_free', False):
                    result_text += "   📌 <i>Выходной</i>\n"
                if emp.get('is_assigned', False):
                    result_text += f"   ✅ <i>Уже назначен на {found_date}</i>\n"
                result_text += "\n"
            
            ensure_excel_path(week_start)
            excel_path = excel_exporter.export_free_employees_to_excel(all_employees, f"{found_day}_all", week_start)
            try:
                with open(excel_path, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=user_id,
                        document=f,
                        filename=f"Все_{found_day}_{week_start}.xlsx",
                        caption=f"📁 <b>Все сотрудники на {found_day} ({found_date})</b>\n📅 {found_day}\n👥 {len(all_employees)} человек",
                        parse_mode='HTML'
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки Excel: {e}")
        
        if all_employees:
            not_assigned_employees = [e for e in all_employees if not e.get('is_assigned', False)]
            
            if not_assigned_employees:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📩 Wyślij zmianę", callback_data="broadcast_shift")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
                ])
                
                await update.message.reply_text(
                    result_text + "\n\n" + f"{format_info('Нажмите кнопку, чтобы отправить смену сотрудникам, указавшим этот день')}\n"
                    f"ℹ️ <i>Смена будет отправлена всем, кто указал {found_day} в графике (включая выходные)</i>",
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
                
                temp_data[user_id] = {
                    "broadcast_day": found_day,
                    "broadcast_date": found_date,
                    "free_employees": [e['full_name'] for e in not_assigned_employees]
                }
                user_states[user_id] = "after_find_employees"
            else:
                await update.message.reply_text(
                    result_text + "\n\n" + f"{format_success('Все сотрудники уже назначены на этот день!')}",
                    reply_markup=get_admin_reply_keyboard(),
                    parse_mode='HTML'
                )
                user_states[user_id] = None
        else:
            await update.message.reply_text(
                f"{format_error('Нет сотрудников, указавших этот день в графике')}",
                reply_markup=get_admin_reply_keyboard(),
                parse_mode='HTML'
            )
            user_states[user_id] = None
        
        return
    
    # ========== ПОСЛЕ ПОИСКА ==========
    if user_states.get(user_id) == "after_find_employees":
        if not is_admin(user_id):
            return
        return
    
    # ========== МАССОВАЯ РАССЫЛКА СМЕНЫ ==========
    if user_states.get(user_id) == "waiting_broadcast_shift_data":
        if not is_admin(user_id):
            return
        
        # \d{1,2} — работает 4:00 и 04:00; любые отели (Sofitel, Hilton, Mercure...)
        shift_pattern = r'^(.+?)\s+(\d{1,2}\.\d{1,2}\.\d{4})\s*\(\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*\)$'
        shift_match = re.match(shift_pattern, text.strip())
        
        if not shift_match:
            await update.message.reply_text(
                f"{format_error('Nie udało się rozpoznać zmiany')}\n\n"
                f"{format_info('Sprawdź format:')}\n"
                f"<code>Sofitel Śniadania 19.08.2026(16:00-04:00)</code>\n"
                f"<code>Hilton Floor 21.08.2026(12:00-22:00)</code>\n"
                f"<code>Mercure 21.08.2026(8:00-16:00)</code>\n"
                f"<code>Novotel centrum 22.08.2026(10:00-18:00)</code>",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        hotel = shift_match.group(1).strip()
        date = shift_match.group(2).strip()
        time_start = shift_match.group(3).strip()
        time_end = shift_match.group(4).strip()
        
        free_employees = temp_data.get(user_id, {}).get("free_employees", [])
        shift_limit = temp_data.get(user_id, {}).get("shift_limit", 1)
        
        if not free_employees:
            await update.message.reply_text(
                f"{format_error('Brak wolnych pracowników')}",
                parse_mode='HTML',
                reply_markup=get_admin_reply_keyboard()
            )
            user_states[user_id] = None
            temp_data.pop(user_id, None)
            return
        
        shift_data = {
            'hotel': hotel,
            'date': date,
            'time_start': time_start,
            'time_end': time_end,
            'max_employees': shift_limit
        }
        
        shift_id = await db.add_shift_to_user(0, shift_data)
        temp_data[user_id]["shift_id"] = shift_id
        
        sent_count = 0
        all_users = await db.get_all_users_with_names()
        
        for user in all_users:
            if user['full_name'] in free_employees:
                try:
                    await context.bot.send_message(
                        chat_id=user['user_id'],
                        text=(
                            f"{format_header('NOWA ZMIANA!', '📋')}"
                            f"📍 <b>{hotel}</b>\n"
                            f"📆 {date}\n"
                            f"⏰ {time_start}-{time_end}\n\n"
                            f"{format_info('Zmiana jest dostępna do potwierdzenia!')}\n"
                            f"👥 <b>Нужно сотрудников:</b> {shift_limit}\n"
                            f"✅ <b>Уже подтвердили:</b> 0 / {shift_limit}\n\n"
                            "💡 <i>Kto pierwszy potwierdzi - ten dostanie zmianę</i>\n"
                            f"ℹ️ <i>После {shift_limit} подтверждений смена закроется</i>"
                        ),
                        parse_mode='HTML',
                        reply_markup=get_shift_confirmation_keyboard(shift_id)
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Błąd wysyłki do {user['user_id']}: {e}")
        
        await update.message.reply_text(
            f"{format_success('Zmiana rozesłana!')}\n\n"
            f"📤 Wysłano: <b>{sent_count}</b> pracownikom\n"
            f"📍 <b>{hotel}</b>\n"
            f"📆 {date}\n"
            f"⏰ {time_start}-{time_end}\n"
            f"👥 <b>Лимит:</b> {shift_limit} сотрудников\n\n"
            f"{format_info('Kto pierwszy potwierdzi - ten dostanie zmianę')}\n"
            f"ℹ️ <i>После {shift_limit} подтверждений смена закроется</i>",
            parse_mode='HTML',
            reply_markup=get_admin_reply_keyboard()
        )
        
        user_states[user_id] = None
        temp_data.pop(user_id, None)
        return
    
    # ========== ЕДИНИЧНАЯ СМЕНА ДЛЯ СОТРУДНИКА ==========
    if user_states.get(user_id) == "waiting_single_shift_data":
        if not is_admin(user_id):
            return
        
        shift_pattern = r'^(.+?)\s+(\d{1,2}\.\d{1,2}\.\d{4})\s*\(\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*\)$'
        shift_match = re.match(shift_pattern, text.strip())
        
        if not shift_match:
            await update.message.reply_text(
                f"{format_error('Nie udało się rozpoznać zmiany')}\n\n"
                f"{format_info('Sprawdź format:')}\n"
                f"<code>Sofitel Śniadania 19.08.2026(16:00-04:00)</code>\n"
                f"<code>Hilton Floor 21.08.2026(12:00-22:00)</code>\n"
                f"<code>Mercure 21.08.2026(8:00-16:00)</code>\n"
                f"<code>Novotel centrum 22.08.2026(10:00-18:00)</code>",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        hotel = shift_match.group(1).strip()
        date = shift_match.group(2).strip()
        time_start = shift_match.group(3).strip()
        time_end = shift_match.group(4).strip()
        
        selected_employee = temp_data.get(user_id, {}).get("selected_employee", "")
        
        users = await db.get_all_users_with_names()
        target_user = None
        for u in users:
            if u['full_name'].lower() == selected_employee.lower():
                target_user = u
                break
        
        if not target_user:
            await update.message.reply_text(
                f"{format_error('Сотрудник не найден')}",
                parse_mode='HTML',
                reply_markup=get_admin_reply_keyboard()
            )
            user_states[user_id] = None
            temp_data.pop(user_id, None)
            return
        
        shift_data = {
            'hotel': hotel,
            'date': date,
            'time_start': time_start,
            'time_end': time_end,
            'max_employees': 1
        }
        
        shift_id = await db.add_shift_to_user(target_user['user_id'], shift_data)
        
        await context.bot.send_message(
            chat_id=target_user['user_id'],
            text=(
                f"{format_header('NOWA ZMIANA!', '📋')}"
                f"📍 <b>{hotel}</b>\n"
                f"📆 {date}\n"
                f"⏰ {time_start}-{time_end}\n\n"
                f"{format_info('Potwierdź lub odrzuć zmianę')}"
            ),
            parse_mode='HTML',
            reply_markup=get_shift_confirmation_keyboard(shift_id)
        )
        
        await update.message.reply_text(
            f"{format_success('Zmiana przypisana!')}\n\n"
            f"👤 <b>Pracownik:</b> {selected_employee}\n"
            f"📍 <b>Hotel:</b> {hotel}\n"
            f"📆 {date}\n"
            f"⏰ {time_start}-{time_end}\n\n"
            f"{format_info('Pracownik otrzymał powiadomienie i czeka na potwierdzenie')}",
            parse_mode='HTML',
            reply_markup=get_admin_reply_keyboard()
        )
        
        user_states[user_id] = None
        temp_data.pop(user_id, None)
        return
    
    # ========== ВВОД ГОТОВОГО ГРАФИКА (РАССЫЛКА) ==========
    if user_states.get(user_id) == "waiting_final_schedule":
        if not is_admin(user_id):
            return
        
        # График + опциональный текст после "---"
        schedule_body = text
        extra_notes = ""
        if "\n---" in text or text.strip().startswith("---"):
            parts = text.split("---", 1)
            schedule_body = parts[0].strip()
            extra_notes = parts[1].strip() if len(parts) > 1 else ""
        
        parsed_schedules = parse_schedule_text(schedule_body)
        
        if not parsed_schedules:
            await update.message.reply_text(
                f"{format_error('Не удалось распознать график')}\n\n" +
                f"{format_info('Проверьте формат:')}\n" +
                "<code>Hotel 20.08.2026(08:00-16:00) - Ivan Ivanov</code>\n\n" +
                f"{format_info('Или нажмите «Главное меню» для отмены')}",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        users = await db.get_all_users_with_names()
        user_map = {}
        for u in users:
            normalized_name = ' '.join(u['full_name'].split()).lower()
            user_map[normalized_name] = u
        
        user_schedules = {}
        not_found = []
        
        for name, shifts in parsed_schedules.items():
            normalized_name = ' '.join(name.split()).lower()
            
            if normalized_name in user_map:
                user_id_found = user_map[normalized_name]['user_id']
                if user_id_found not in user_schedules:
                    user_schedules[user_id_found] = {
                        'name': user_map[normalized_name]['full_name'],
                        'shifts': []
                    }
                user_schedules[user_id_found]['shifts'].extend(shifts)
            else:
                not_found.append(name)
        
        if not_found:
            await update.message.reply_text(
                f"{format_warning('Не найдены (им не уйдёт):')}\n\n" +
                "\n".join(not_found) + "\n\n" +
                f"{format_info('Остальным найденным график будет отправлен')}",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            # продолжаем рассылку найденным — без return
        
        if not user_schedules:
            await update.message.reply_text(
                f"{format_error('Не найдено ни одного сотрудника для рассылки')}",
                parse_mode='HTML',
                reply_markup=get_admin_reply_keyboard()
            )
            return
        
        week_start = get_broadcast_week_start_str()
        await db.clear_assigned_shifts_for_week(week_start)
        
        sent_count = 0
        failed_count = 0
        failed_users = []
        
        for user_id_db, data in user_schedules.items():
            try:
                for shift in data['shifts']:
                    try:
                        date_obj = datetime.strptime(shift['date'], "%d.%m.%Y")
                        day_name = date_obj.strftime("%A")
                        days_pl = {
                            'Monday': 'Poniedziałek',
                            'Tuesday': 'Wtorek',
                            'Wednesday': 'Środa',
                            'Thursday': 'Czwartek',
                            'Friday': 'Piątek',
                            'Saturday': 'Sobota',
                            'Sunday': 'Niedziela'
                        }
                        day_pl = days_pl.get(day_name, day_name)
                    except:
                        day_pl = shift['date']
                    
                    await db.assign_shift(
                        user_id=user_id_db,
                        day=day_pl,
                        date=shift['date'],
                        hotel=shift['hotel'],
                        time_start=shift['time_start'],
                        time_end=shift['time_end'],
                        assigned_by=user_id,
                        week_start=week_start
                    )
                
                text_msg = f"{format_header('Twój grafik', '📋')}"
                text_msg += f"📅 <b>{get_week_range_text()}</b>\n"
                text_msg += "─" * 35 + "\n\n"
                
                shifts_by_date = {}
                for shift in data['shifts']:
                    date = shift['date']
                    if date not in shifts_by_date:
                        shifts_by_date[date] = []
                    shifts_by_date[date].append(shift)
                
                for date in sorted(shifts_by_date.keys()):
                    text_msg += f"📆 <b>{date}</b>\n"
                    for shift in shifts_by_date[date]:
                        text_msg += f"📍 <b>{shift['hotel']}</b>\n"
                        text_msg += f"⏰ {shift['time_start']}-{shift['time_end']}\n"
                    text_msg += "\n"
                
                text_msg += f"{format_info('Udanej pracy 💪')}"
                
                if extra_notes:
                    text_msg += "\n\n" + "─" * 35 + "\n"
                    text_msg += f"📌 <b>Informacja:</b>\n{html.escape(extra_notes)}"
                
                await context.bot.send_message(
                    chat_id=user_id_db,
                    text=text_msg,
                    parse_mode='HTML'
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Ошибка отправки пользователю {user_id_db}: {e}")
                failed_count += 1
                failed_users.append(data['name'])
        
        user_states[user_id] = None
        
        result_text = f"{format_success('Рассылка выполнена!')}\n\n"
        result_text += f"📤 Отправлено: <b>{sent_count}</b> сотрудников\n"
        result_text += f"❌ Ошибок: <b>{failed_count}</b>"
        if failed_users:
            result_text += f"\n\nНе доставлено: {', '.join(failed_users)}"
        
        await update.message.reply_text(
            result_text,
            reply_markup=get_admin_reply_keyboard(),
            parse_mode='HTML'
        )
        return
    
    # ========== РЕДАКТИРОВАНИЕ ГОТОВОГО ГРАФИКА (ОБРАБОТКА) ==========
    if user_states.get(user_id) == "waiting_edit_final_schedule":
        if not is_admin(user_id):
            return
        
        schedule_body = text
        extra_notes = ""
        if "\n---" in text or text.strip().startswith("---"):
            parts = text.split("---", 1)
            schedule_body = parts[0].strip()
            extra_notes = parts[1].strip() if len(parts) > 1 else ""
        
        parsed_schedules = parse_schedule_text(schedule_body)
        
        if not parsed_schedules:
            await update.message.reply_text(
                f"{format_error('Не удалось распознать график')}\n\n" +
                f"{format_info('Проверьте формат:')}\n" +
                "<code>Hotel 20.08.2026(08:00-16:00) - Ivan Ivanov</code>\n\n" +
                f"{format_info('Или нажмите «Главное меню» для отмены')}",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            return
        
        users = await db.get_all_users_with_names()
        user_map = {}
        for u in users:
            normalized_name = ' '.join(u['full_name'].split()).lower()
            user_map[normalized_name] = u
        
        user_schedules = {}
        not_found = []
        
        for name, shifts in parsed_schedules.items():
            normalized_name = ' '.join(name.split()).lower()
            
            if normalized_name in user_map:
                user_id_found = user_map[normalized_name]['user_id']
                if user_id_found not in user_schedules:
                    user_schedules[user_id_found] = {
                        'name': user_map[normalized_name]['full_name'],
                        'shifts': []
                    }
                user_schedules[user_id_found]['shifts'].extend(shifts)
            else:
                not_found.append(name)
        
        if not_found:
            await update.message.reply_text(
                f"{format_warning('Не найдены (им не уйдёт):')}\n\n" +
                "\n".join(not_found) + "\n\n" +
                f"{format_info('Остальным найденным график будет отправлен')}",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline()
            )
            # продолжаем рассылку найденным — без return
        
        if not user_schedules:
            await update.message.reply_text(
                f"{format_error('Не найдено ни одного сотрудника для обновления')}",
                parse_mode='HTML',
                reply_markup=get_admin_reply_keyboard()
            )
            return
        
        week_start = temp_data.get(user_id, {}).get("edit_week_start", get_week_start_str())
        
        await db.clear_assigned_shifts_for_week(week_start)
        
        updated_count = 0
        failed_count = 0
        failed_users = []
        
        for user_id_db, data in user_schedules.items():
            try:
                for shift in data['shifts']:
                    try:
                        date_obj = datetime.strptime(shift['date'], "%d.%m.%Y")
                        day_name = date_obj.strftime("%A")
                        days_pl = {
                            'Monday': 'Poniedziałek',
                            'Tuesday': 'Wtorek',
                            'Wednesday': 'Środa',
                            'Thursday': 'Czwartek',
                            'Friday': 'Piątek',
                            'Saturday': 'Sobota',
                            'Sunday': 'Niedziela'
                        }
                        day_pl = days_pl.get(day_name, day_name)
                    except:
                        day_pl = shift['date']
                    
                    await db.assign_shift(
                        user_id=user_id_db,
                        day=day_pl,
                        date=shift['date'],
                        hotel=shift['hotel'],
                        time_start=shift['time_start'],
                        time_end=shift['time_end'],
                        assigned_by=user_id,
                        week_start=week_start
                    )
                
                text_msg = f"🔄 <b>ОБНОВЛЕННЫЙ ГРАФИК</b>\n"
                text_msg += "─────────────────────\n\n"
                text_msg += f"📅 <b>{get_week_range_text()}</b>\n\n"
                
                shifts_by_date = {}
                for shift in data['shifts']:
                    date = shift['date']
                    if date not in shifts_by_date:
                        shifts_by_date[date] = []
                    shifts_by_date[date].append(shift)
                
                for date in sorted(shifts_by_date.keys()):
                    for shift in shifts_by_date[date]:
                        text_msg += f"📍 <b>{shift['hotel']}</b>\n"
                        text_msg += f"📆 {shift['date']}\n"
                        text_msg += f"⏰ {shift['time_start']}-{shift['time_end']}\n\n"
                
                text_msg += f"{format_info('График обновлен! Проверьте изменения 💪')}"
                if extra_notes:
                    text_msg += "\n\n" + "─" * 35 + "\n"
                    text_msg += f"📌 <b>Informacja:</b>\n{html.escape(extra_notes)}"
                
                await context.bot.send_message(
                    chat_id=user_id_db,
                    text=text_msg,
                    parse_mode='HTML'
                )
                updated_count += 1
            except Exception as e:
                logger.error(f"Ошибка обновления для {user_id_db}: {e}")
                failed_count += 1
                failed_users.append(data['name'])
        
        user_states[user_id] = None
        temp_data.pop(user_id, None)
        
        result_text = f"{format_success('График обновлен!')}\n\n"
        result_text += f"📤 Обновлено: <b>{updated_count}</b> сотрудников\n"
        result_text += f"❌ Ошибок: <b>{failed_count}</b>"
        if failed_users:
            result_text += f"\n\nНе доставлено: {', '.join(failed_users)}"
        
        await update.message.reply_text(
            result_text,
            parse_mode='HTML',
            reply_markup=get_admin_reply_keyboard()
        )
        return

def parse_schedule_text(text):
    """
    Парсинг графика. Поддерживает два формата:
    1. Hotel: President
       20.08.2026
       08:00-12:00
       Anton Rozehan
       
       21.08.2026
       08:00-12:00
       Anton Rozehan
       Alex (новый многострочный)
    """
    schedules = {}
    lines = text.strip().split('\n')
    
    # Проверяем какой формат
    is_new_format = False
    for line in lines[:5]:
        if line.strip().lower().startswith('hotel:'):
            is_new_format = True
            break
    
    if is_new_format:
        return parse_schedule_text_new_format(text)
    
    # Старый формат
    pattern = r'^(.+?)\s+(\d{2}\.\d{2}\.\d{4})\s*\(\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*\)\s*-\s*(.+?)\s*$'
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        match = re.match(pattern, line)
        if not match:
            logger.warning(f"Не удалось распарсить строку: {line}")
            continue
        
        hotel = ' '.join(match.group(1).split())
        date = match.group(2).strip()
        time_start = match.group(3).strip()
        time_end = match.group(4).strip()
        names_str = match.group(5).strip()
        
        names = [' '.join(n.split()) for n in names_str.split(',') if n.strip()]
        
        for name in names:
            if name not in schedules:
                schedules[name] = []
            schedules[name].append({
                'hotel': hotel,
                'date': date,
                'time_start': time_start,
                'time_end': time_end
            })
    
    return schedules

def parse_schedule_text_new_format(text):
    """
    Парсинг графика в новом формате:
    Hotel: 
    20.07.2026
    08:00-12:00
    Dvoineu Ivan
    Makarenko Mariia
    """
    schedules = {}
    lines = text.strip().split('\n')
    
    current_hotel = None
    current_date = None
    current_time_start = None
    current_time_end = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Определяем отель
        if line.lower().startswith('hotel'):
            current_hotel = line.split(':', 1)[1].strip() if ':' in line else line
            continue
        
        # Определяем дату (формат DD.MM.YYYY)
        date_match = re.match(r'^(\d{2}\.\d{2}\.\d{4})$', line)
        if date_match:
            current_date = date_match.group(1)
            continue
        
        # Определяем время (формат HH:MM-HH:MM)
        time_match = re.match(r'^(\d{1,2}:\d{2})-(\d{1,2}:\d{2})$', line)
        if time_match:
            current_time_start = time_match.group(1)
            current_time_end = time_match.group(2)
            continue
        
        # Это имя сотрудника
        if current_hotel and current_date and current_time_start:
            # Убираем нумерацию "1.Tkach Polina" -> "Tkach Polina"
            name = re.sub(r'^\d+\.\s*', '', line)
            name = ' '.join(name.split())
            
            if name and not re.match(r'^\d{1,2}:\d{2}$', name):  # Пропускаем если это время
                if name not in schedules:
                    schedules[name] = []
                
                schedules[name].append({
                    'hotel': current_hotel,
                    'date': current_date,
                    'time_start': current_time_start,
                    'time_end': current_time_end
                })
    
    return schedules

# ========== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ RENDER ==========

async def health_check():
    """Функция для health check на Render"""
    return "Bot is running"

def main():
    """Запуск бота с поддержкой Render"""
    print("🚀 Запуск бота...")
    
    # Создаем директорию для файлов если её нет
    os.makedirs("/tmp/bot_files", exist_ok=True)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(db.init_db())
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    job_queue = application.job_queue
    if job_queue:
        # Напоминания в группу: пт и сб, каждые 6 часов
        job_queue.run_repeating(send_reminder, interval=21600, first=10)
        print(f"✅ Напоминания: пт/сб каждые 6 часов → группа {GROUP_CHAT_ID}")
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("restart", restart_command))
    
    application.add_handler(CallbackQueryHandler(handle_buttons))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    
    print("✅ Бот успешно запущен!")
    print(f"📨 Нажмите /start в Telegram")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print("⏹ Нажмите Ctrl+C для остановки")
    
    # Определяем режим работы
    is_render = os.environ.get("RENDER") == "true"
    port = int(os.environ.get("PORT", 10000))
    
    if is_render:
        # Режим Webhook для Render
        webhook_url = os.environ.get("RENDER_EXTERNAL_URL")
        if webhook_url:
            print(f"✅ Запуск в режиме Webhook на порту {port}")
            print(f"🌐 Webhook URL: {webhook_url}/{BOT_TOKEN}")
            application.run_webhook(
                listen="0.0.0.0",
                port=port,
                url_path=BOT_TOKEN,
                webhook_url=f"{webhook_url}/{BOT_TOKEN}"
            )
        else:
            print("⚠️ RENDER_EXTERNAL_URL не найден, запуск в режиме Polling")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
    else:
        # Режим Polling для локальной разработки
        print("✅ Запуск в режиме Polling")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹ Бот остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)