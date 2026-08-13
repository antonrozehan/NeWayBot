import sqlite3

print("🗑 ОЧИСТКА ВСЕХ ДАННЫХ...")

# Подключаемся к базе
conn = sqlite3.connect('schedule.db')
cursor = conn.cursor()

# Получаем список всех таблиц
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

# Очищаем каждую таблицу
for table in tables:
    table_name = table[0]
    # Пропускаем системные таблицы
    if table_name not in ['sqlite_sequence']:
        cursor.execute(f"DELETE FROM {table_name}")
        print(f"✅ Очищена таблица: {table_name}")

# Сбрасываем автоинкремент
cursor.execute("DELETE FROM sqlite_sequence;")

conn.commit()
conn.close()

print("\n✅ ВСЕ ДАННЫЕ УСПЕШНО ОЧИЩЕНЫ!")
print("📌 Перезапустите бота командой: python bot.py")