import re
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

# ========== ФУНКЦИИ ДАТ ==========

def get_current_week_start():
    """Возвращает дату начала текущей недели (понедельник)"""
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%d.%m.%Y")

def get_current_week_end():
    """Возвращает дату окончания текущей недели (воскресенье)"""
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return sunday.strftime("%d.%m.%Y")

def get_next_week_start():
    """Возвращает дату начала следующей недели (понедельник)"""
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    next_monday = monday + timedelta(days=7)
    return next_monday.strftime("%d.%m.%Y")

def get_next_week_end():
    """Возвращает дату окончания следующей недели (воскресенье)"""
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    next_monday = monday + timedelta(days=7)
    next_sunday = next_monday + timedelta(days=6)
    return next_sunday.strftime("%d.%m.%Y")

def get_current_monday_date():
    """Понедельник текущей календарной недели"""
    today = datetime.now().date()
    return today - timedelta(days=today.weekday())


def get_next_monday_date():
    """Понедельник следующей календарной недели"""
    return get_current_monday_date() + timedelta(days=7)


def get_week_start_str():
    """
    Для таблиц, Excel, «Не назначенные», «Все графики»:
    ВСЕГДА текущая неделя (пн–вс, где мы сейчас).
    Сегодня пн 17.08 → 2026-08-17 (17–23), НЕ 24–30.
    """
    return get_current_monday_date().strftime("%Y-%m-%d")


def get_submit_week_start_str():
    """
    Куда сохранять график при отправке официантом (пт/сб):
    следующая неделя.
    """
    return get_next_monday_date().strftime("%Y-%m-%d")


def get_week_range_text():
    """Диапазон ТЕКУЩЕЙ недели для сообщений и Excel"""
    start = get_current_monday_date()
    end = start + timedelta(days=6)
    return f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"


def get_week_range_from_str(week_start: str) -> str:
    """Диапазон по понедельнику YYYY-MM-DD"""
    start = datetime.strptime(week_start[:10], "%Y-%m-%d").date()
    end = start + timedelta(days=6)
    return f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"


def parse_week_range_input(text: str):
    """
    13.08-19.08 или 13.08.2026 - 19.08.2026
    Возвращает (week_start YYYY-MM-DD понедельника, 'dd.mm.yyyy - dd.mm.yyyy') или None.
    """
    if not text:
        return None
    raw = text.strip().replace('–', '-').replace('—', '-')
    raw = re.sub(r'\s+', '', raw)
    year = datetime.now().year
    m = re.match(
        r'^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?(?:-(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?)?$',
        raw
    )
    if not m:
        return None
    d1, mo1, y1, d2, mo2, y2 = m.groups()
    y1 = int(y1) if y1 else year
    try:
        start = datetime(y1, int(mo1), int(d1)).date()
    except ValueError:
        return None
    monday = start - timedelta(days=start.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), f"{monday.strftime('%d.%m.%Y')} - {sunday.strftime('%d.%m.%Y')}"


def get_broadcast_week_start_str() -> str:
    """
    Куда писать готовую рассылку:
    пт–вс — на СЛЕДУЮЩУЮ неделю (сбор уже идёт),
    пн–чт — на текущую.
    """
    if datetime.now().weekday() >= 4:  # Fri Sat Sun
        return get_submit_week_start_str()
    return get_week_start_str()

def format_week(start, end):
    """Форматирует неделю в читаемый вид"""
    return f"{start} - {end}"

# ========== КЛАВИАТУРЫ ==========

def get_main_reply_keyboard():
    """Клавиатура для обычных пользователей"""
    keyboard = [
        ["📝 Отправить график", "✏️ Изменить график"],
        ["📋 Мой график"],
        ["❓ Помощь"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_reply_keyboard():
    """Клавиатура для администратора"""
    keyboard = [
        ["📊 Все графики", "📁 Excel-отчет"],
        ["📤 Рассылка", "✏️ Редактировать график"],
        ["🔍 Свободные", "📋 Не назначенные"],
        ["📈 Статистика"],
        ["❓ Помощь"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_main_menu_inline():
    """Инлайн-кнопка для возврата в главное меню"""
    keyboard = [
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_shift_confirmation_keyboard(shift_id):
    """Клавиатура для подтверждения/отказа от смены"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_shift_{shift_id}"),
            InlineKeyboardButton("❌ Отказаться", callback_data=f"decline_shift_{shift_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== ФУНКЦИИ ДЛЯ ФОРМАТИРОВАНИЯ ==========

def format_header(text, icon="📋"):
    """Форматирует заголовок"""
    return f"{icon} <b>{text}</b>\n─────────────────────\n\n"

def format_info(text):
    """Форматирует информационное сообщение"""
    return f"ℹ️ {text}\n"

def format_success(text):
    """Форматирует сообщение об успехе"""
    return f"✅ {text}\n"

def format_error(text):
    """Форматирует сообщение об ошибке"""
    return f"❌ {text}\n"

def format_warning(text):
    """Форматирует предупреждение"""
    return f"⚠️ {text}\n"

# ========== ФУНКЦИИ ДЛЯ ПАРСИНГА ==========

def parse_shift_input(text):
    """
    Парсинг ввода смены.
    Формат: Hotel Sofitel Śniadania 19.08.2026(16:00-4:00)
    """
    import re
    pattern = r'^(.+?)\s+(\d{2}\.\d{2}\.\d{4})\((\d{1,2}:\d{2})-(\d{1,2}:\d{2})\)$'
    match = re.match(pattern, text.strip())
    
    if match:
        return {
            'hotel': match.group(1).strip(),
            'date': match.group(2).strip(),
            'time_start': match.group(3).strip(),
            'time_end': match.group(4).strip()
        }
    return None

def parse_schedule_line(line):
    """
    Парсинг строки графика.
    Формат: Poniedziałek: cały dzień
    """
    import re
    # Ищем день недели
    days = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
    days_ru = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
    all_days = days + days_ru
    
    for day in all_days:
        if day.lower() in line.lower():
            # Извлекаем информацию после дня
            parts = line.split(':', 1)
            if len(parts) > 1:
                info = parts[1].strip()
            else:
                info = line.replace(day, '').strip()
            
            return {
                'day': day,
                'info': info if info else 'cały dzień'
            }
    return None

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def get_days_order():
    """Возвращает порядок дней недели"""
    return ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']

def get_day_date(day_name, week_start_str):
    """
    Получает дату для дня недели
    week_start_str - дата понедельника в формате YYYY-MM-DD
    """
    from datetime import datetime, timedelta
    
    days_order = get_days_order()
    week_start = datetime.strptime(week_start_str, "%Y-%m-%d").date()
    
    for i, day in enumerate(days_order):
        if day.lower() == day_name.lower():
            date_obj = week_start + timedelta(days=i)
            return date_obj.strftime("%d.%m.%Y")
    return None

def is_free_day(text):
    """Проверяет, является ли день выходным"""
    free_words = ['wolne', 'nie mogę', 'выходной', 'не могу', 'off', 'free', 'wolny']
    return any(word in text.lower() for word in free_words)

def extract_time_info(text):
    """Извлекает информацию о времени из текста"""
    import re
    
    time_from = ""
    time_to = ""
    
    # Ищем "od HH:MM"
    od_match = re.search(r'od\s*(\d{1,2}:\d{2})', text, re.IGNORECASE)
    if od_match:
        time_from = od_match.group(1)
    
    # Ищем "do HH:MM"
    do_match = re.search(r'do\s*(\d{1,2}:\d{2})', text, re.IGNORECASE)
    if do_match:
        time_to = do_match.group(1)
    
    # Ищем "HH:MM-HH:MM"
    range_match = re.search(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})', text)
    if range_match:
        time_from = range_match.group(1)
        time_to = range_match.group(2)
    
    # Проверяем на "cały dzień"
    if 'cały dzień' in text.lower() or 'caly dzien' in text.lower():
        return {
            'from': 'od rana',
            'to': 'do wieczora',
            'display': 'cały dzień'
        }
    
    if time_from and time_to:
        display = f"od {time_from} do {time_to}"
    elif time_from:
        display = f"od {time_from}"
    elif time_to:
        display = f"do {time_to}"
    else:
        display = text if text else "cały dzień"
    
    return {
        'from': time_from,
        'to': time_to,
        'display': display
    }

def get_day_pl_from_date(date_str):
    """Получает название дня недели на польском из даты"""
    from datetime import datetime
    
    days_pl = {
        'Monday': 'Poniedziałek',
        'Tuesday': 'Wtorek',
        'Wednesday': 'Środa',
        'Thursday': 'Czwartek',
        'Friday': 'Piątek',
        'Saturday': 'Sobota',
        'Sunday': 'Niedziela'
    }
    
    try:
        date_obj = datetime.strptime(date_str, "%d.%m.%Y")
        day_name = date_obj.strftime("%A")
        return days_pl.get(day_name, day_name)
    except:
        return date_str

def get_week_dates(week_start_str):
    """Получает даты для всех дней недели"""
    from datetime import datetime, timedelta
    
    days_order = get_days_order()
    week_start = datetime.strptime(week_start_str, "%Y-%m-%d").date()
    
    dates = {}
    for i, day in enumerate(days_order):
        date_obj = week_start + timedelta(days=i)
        dates[day] = date_obj.strftime("%d.%m.%Y")
    
    return dates