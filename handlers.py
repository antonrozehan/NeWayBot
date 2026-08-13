import logging
import asyncio
import re
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID
from database import Database
from excel_exporter import ExcelExporter
from formatters import *
from utils import *
from templates import get_empty_schedule_template

logger = logging.getLogger(__name__)
db = Database()
excel_exporter = ExcelExporter()
user_states = {}
temp_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    await db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    is_admin = user.id == ADMIN_ID
    
    current_week = format_week(get_current_week_start(), get_current_week_end())
    next_week = format_week(get_next_week_start(), get_next_week_end())
    
    if is_admin:
        keyboard = get_admin_reply_keyboard()
        welcome = (
            "👋 <b>Добрый день, Администратор!</b>\n\n"
            f"{format_header('Панель управления', '📋')}"
            f"📅 Текущая неделя: <b>{current_week}</b>\n"
            f"📅 Следующая неделя: <b>{next_week}</b>\n\n"
            f"{format_info('Выберите действие в меню ниже')}\n\n"
            f"💡 <i>Кнопки всегда под рукой</i>"
        )
    else:
        keyboard = get_main_reply_keyboard()
        has_schedule = await db.get_user_schedule(user.id) is not None
        
        welcome = (
            "👋 <b>Witaj!</b>\n\n"
            f"{format_header('Panel pracownika', '👤')}"
            f"📅 Następny tydzień: <b>{next_week}</b>\n\n"
        )
        
        if not has_schedule:
            welcome += f"{format_info('Вы ещё не отправили график')}\n"
            welcome += f"💡 <i>Нажмите «📝 Отправить график»</i>\n\n"
        else:
            welcome += f"{format_success('График уже отправлен')}\n"
            welcome += f"💡 <i>Можно изменить в любое время</i>\n\n"
        
        welcome += f"💡 <i>График можно отправить в любой день</i>"
    
    await update.message.reply_text(
        welcome,
        parse_mode='HTML',
        reply_markup=keyboard
    )

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"{format_header('Мой ID', '🆔')}"
        f"<code>{user_id}</code>\n\n"
        f"{format_info('Сохраните этот ID')}",
        parse_mode='HTML'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = user_id == ADMIN_ID
    
    if is_admin:
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
            f"{format_info('Используйте кнопки внизу')}"
        )
    else:
        text = (
            f"{format_header('Pomoc', '❓')}"
            "📌 <b>Dostępne akcje:</b>\n\n"
            "📝 <b>Wyślij grafik</b>\n"
            "  └ Podaj dni i godziny pracy\n\n"
            "✏️ <b>Zmień grafik</b>\n"
            "  └ Zaktualizuj swój grafik\n\n"
            "📋 <b>Mój grafik</b>\n"
            "  └ Sprawdź swój grafik\n\n"
            f"{format_info('Przykład grafiku:')}\n"
            "<code>Poniedziałek: cały dzień</code>\n"
            "<code>Wtorek: od 10:00</code>\n"
            "<code>Środa: do 16:00</code>\n\n"
            f"{format_info('Pamiętaj - podaj dzień tygodnia!')}"
        )
    
    await update.message.reply_text(text, parse_mode='HTML')