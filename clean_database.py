import asyncio
import logging
from datetime import datetime
from database import Database
from config import BOT_TOKEN, ADMIN_ID
from telegram import Bot

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()
bot = Bot(token=BOT_TOKEN)

async def clean_database():
    """Очистка всех таблиц в базе данных"""
    try:
        print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Начинаю очистку базы данных...")
        
        await db.init_db()
        
        # Очищаем все таблицы
        await db.clear_all_data()
        
        print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] База данных успешно очищена")
        
        # Отправляем уведомление админу
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "🧹 <b>БАЗА ДАННЫХ ОЧИЩЕНА</b>\n"
                "─────────────────────\n\n"
                f"📅 <b>Дата очистки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                "✅ Все таблицы очищены\n"
                "🔄 Бот готов к новому циклу"
            ),
            parse_mode='HTML'
        )
        print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] Уведомление отправлено админу")
        
    except Exception as e:
        print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] Ошибка очистки базы данных: {e}")
        logger.error(f"Ошибка очистки: {e}")

async def main():
    """Автоматическая очистка каждые 10 секунд"""
    print("🚀 Запуск автоматической очистки базы данных...")
    print("⏱ Интервал: каждые 10 секунд")
    print("⏹ Нажмите Ctrl+C для остановки\n")
    
    counter = 0
    
    while True:
        counter += 1
        print(f"📤 Очистка #{counter}")
        await clean_database()
        print(f"⏳ Ожидание 10 секунд...\n")
        await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹ Остановлено пользователем")
    except Exception as e:
        print(f"❌ Ошибка: {e}")