import re
from datetime import datetime, timedelta

def get_current_week_start():
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    return monday

def get_current_week_end():
    monday = get_current_week_start()
    sunday = monday + timedelta(days=6)
    return sunday

def get_next_week_start():
    current_monday = get_current_week_start()
    next_monday = current_monday + timedelta(days=7)
    return next_monday

def get_next_week_end():
    next_monday = get_next_week_start()
    next_sunday = next_monday + timedelta(days=6)
    return next_sunday

def format_week(start_date, end_date):
    return f"{start_date.strftime('%d.%m')} - {end_date.strftime('%d.%m.%Y')}"

def get_week_range_text():
    start = get_next_week_start()
    end = get_next_week_end()
    return f"{start.strftime('%d.%m')} - {end.strftime('%d.%m.%Y')}"

def get_week_start_str():
    return get_next_week_start().strftime("%Y-%m-%d")

def get_current_week_range_text():
    start = get_current_week_start()
    end = get_current_week_end()
    return f"{start.strftime('%d.%m')} - {end.strftime('%d.%m.%Y')}"

def can_submit_schedule():
    return True

def get_days_until_friday():
    today = datetime.now().weekday()
    if today == 6:
        return 5
    elif today == 0:
        return 4
    elif today == 1:
        return 3
    elif today == 2:
        return 2
    elif today == 3:
        return 1
    else:
        return 0