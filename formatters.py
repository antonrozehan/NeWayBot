from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from config import HOTELS, SHIFT_TYPES, BREAKFAST_HOTELS, FLOOR_HOTELS

def format_header(title, icon="📋"):
    return f"{icon} <b>{title}</b>\n" + "─" * 35 + "\n"

def format_success(text):
    return f"✅ <b>{text}</b>"

def format_error(text):
    return f"❌ <b>{text}</b>"

def format_info(text):
    return f"ℹ️ <b>{text}</b>"

def format_warning(text):
    return f"⚠️ <b>{text}</b>"

def get_main_reply_keyboard():
    buttons = [
        ["📝 Отправить график"],
        ["📋 Мой график", "✏️ Изменить график"],
        ["❓ Помощь"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_admin_reply_keyboard():
    buttons = [
        ["📊 Все графики", "📁 Excel-отчет"],
        ["📤 Рассылка", "🔍 Свободные"],
        ["🧹 Очистить графики"],
        ["📋 Не назначенные", "✏️ Редактировать график"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_main_menu_inline():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ])

def get_shift_confirmation_keyboard(shift_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Potwierdzić", callback_data=f"confirm_shift_{shift_id}"),
            InlineKeyboardButton("❌ Odmówić", callback_data=f"decline_shift_{shift_id}")
        ]
    ])

def get_hotel_keyboard():
    """Клавиатура с выбором отеля"""
    buttons = []
    row = []
    for i, hotel in enumerate(HOTELS):
        row.append(InlineKeyboardButton(hotel, callback_data=f"hotel_{i}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🏠 Отмена", callback_data="cancel_hotel")])
    return InlineKeyboardMarkup(buttons)

def get_shift_type_keyboard():
    """Клавиатура с выбором типа смены"""
    buttons = []
    for i, shift_type in enumerate(SHIFT_TYPES):
        buttons.append([InlineKeyboardButton(shift_type, callback_data=f"shift_type_{i}")])
    buttons.append([InlineKeyboardButton("🏠 Отмена", callback_data="cancel_shift_type")])
    return InlineKeyboardMarkup(buttons)

def get_floor_keyboard():
    """Клавиатура с выбором этажа (1-10)"""
    buttons = []
    row = []
    for i in range(1, 11):
        row.append(InlineKeyboardButton(f"Этаж {i}", callback_data=f"floor_{i}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🏠 Отмена", callback_data="cancel_floor")])
    return InlineKeyboardMarkup(buttons)