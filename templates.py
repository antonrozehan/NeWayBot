from config import WEEKDAYS_PL, WEEKDAYS_PL_SHORT

def get_empty_schedule_template():
    template = "📋 <b>TWOJ GRAFIK PRACY</b>\n"
    template += "─────────────────────\n"
    template += "📅 <b>Następny tydzień</b>\n\n"
    
    for day in WEEKDAYS_PL:
        template += f"{day}: ___________\n"
    
    template += "\n"
    template += "─────────────────────\n"
    template += "💡 <i>Przykład wypełnienia:</i>\n"
    template += get_example_schedule()
    
    return template

def get_example_schedule():
    example = "─────────────────────\n"
    example += "Poniedziałek: cały dzień\n"
    example += "Wtorek: od 10:00\n"
    example += "Środa: do 16:00\n"
    example += "Czwartek: od 9:00 do 18:00\n"
    example += "Piątek: nie mogę\n"
    example += "Sobota: wolne\n"
    example += "Niedziela: po południu\n"
    example += "─────────────────────"
    return example

def get_schedule_instruction():
    instruction = (
        "📝 <b>Jak wypełnić grafik?</b>\n\n"
        "1. W każdym dniu wpisz godziny pracy\n"
        "2. Możesz napisać:\n"
        "   • <code>cały dzień</code> - cały dzień\n"
        "   • <code>od 10:00</code> - od 10:00\n"
        "   • <code>do 16:00</code> - do 16:00\n"
        "   • <code>od 9:00 do 18:00</code> - od 9:00 do 18:00\n"
        "   • <code>nie mogę</code> / <code>wolne</code> - dzień wolny\n\n"
        "💡 <i>Ważne: podaj dzień tygodnia!</i>"
    )
    return instruction

def format_schedule_pl(schedule_text):
    return schedule_text