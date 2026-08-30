import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
GROUP_CHAT_ID = -5056870971
DB_PATH = os.getenv('DB_PATH', 'schedule.db')
EXCEL_PATH = os.getenv('EXCEL_PATH', 'schedules.xlsx')
FREE_EMPLOYEES_EXCEL_PATH = os.getenv('FREE_EMPLOYEES_EXCEL_PATH', 'free_employees.xlsx')

# ДНИ НЕДЕЛИ НА ПОЛЬСКОМ
WEEKDAYS_PL = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
WEEKDAYS_PL_SHORT = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Nd']

# ДНИ НЕДЕЛИ НА РУССКОМ
WEEKDAYS_RU = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']

# МАППИНГ ДЛЯ ПОИСКА
DAY_MAPPING = {
    'понедельник': 'Poniedziałek',
    'вторник': 'Wtorek',
    'среда': 'Środa',
    'четверг': 'Czwartek',
    'пятница': 'Piątek',
    'суббота': 'Sobota',
    'воскресенье': 'Niedziela',
    'poniedziałek': 'Poniedziałek',
    'wtorek': 'Wtorek',
    'środa': 'Środa',
    'czwartek': 'Czwartek',
    'piątek': 'Piątek',
    'sobota': 'Sobota',
    'niedziela': 'Niedziela',
    'pon': 'Poniedziałek',
    'wt': 'Wtorek',
    'śr': 'Środa',
    'czw': 'Czwartek',
    'pt': 'Piątek',
    'sob': 'Sobota',
    'nd': 'Niedziela'
}

HOTELS = [
    "Mercure",
    "Regent",
    "Novotel centrum",
    "Sofitel",
    "Presidential",
    "Hilton"
]

# Типы смен
SHIFT_TYPES = [
    "Normal",
    "Śniadania",
    "Presidential Floor"
]

# Отели, для которых доступны Śniadania
BREAKFAST_HOTELS = HOTELS  # Все отели

# Отели, для которых доступен Floor
FLOOR_HOTELS = ["Presidential"]  # Только Presidential