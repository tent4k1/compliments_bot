import telebot
import logging
import time

from threading import Thread
from sched import scheduler
from config import TOKEN
from database import Database
from utils.scheduler import ComplimentScheduler
from handlers.reminders_handlers import Reminders_Handlers
from handlers.weather_handlers import Weather_Handlers
from handlers.user_commands import UserCommands
from handlers.admin_commands import setup_admin_commands
from handlers.list_handlers import List_Handlers
from keyboards.main_menu import Buttons_menu

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger("telebot")
logger.setLevel(logging.DEBUG)

def run_health_check(scheduler): # Фоновая проверка состояния бота
    while True:
        try:
            status = scheduler.check_working()
            logger.info(
                f"Health check: {status['users_count']} users, "
                f"{status['compliments_available']} compliments available"
            )
            time.sleep(300)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            time.sleep(60)

def load_events():
    scheduler = ComplimentScheduler(bot, db)
    events = db.get_all_events()
    for event in events:
        scheduler.schedule_event_reminder(event)
        print(f"Загружено событие: {event[1]}-{event[2]:02d}-{event[3]:02d} в {event[4]}: {event[5]}")

def main():
    try:
        bot = telebot.TeleBot(TOKEN)
        db = Database()
        bm = Buttons_menu()
        wh = Weather_Handlers()
        scheduler = ComplimentScheduler(bot, db)
        lh = List_Handlers(bot, db, bm)
        rh = Reminders_Handlers(bot, db, bm, scheduler)
        uc = UserCommands(bot, db, bm, wh, rh, lh, scheduler)

        restored_users = 0
        for user_id in db.get_subscribed_users():
            try:
                bot.send_message(
                    user_id,
                    "🔔 Бот был перезапущен!\n"
                    "Ваша подписка сохранена, вы продолжите получать комплименты."
                )
                restored_users += 1
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
                db.set_subscription(user_id, False)

        logging.info(f"Restored {restored_users} subscriptions")

        setup_admin_commands(bot, db)

        scheduler.start()

        health_thread = Thread(target=run_health_check, args=(scheduler,), daemon=True)
        health_thread.start()

        @bot.message_handler(commands=['status']) # Команда для проверки статуса
        def handle_status(message):
            status = scheduler.check_working()
            bot.reply_to(
                message,
                f"🤖 Статус бота:\n"
                f"• Состояние: {status['status']}\n"
                f"• Подписчиков: {status['users_count']}\n"
                f"• Доступно комплиментов: {status['compliments_available']}\n"
                f"• Последняя отправка: {status['last_compliment_sent'] or 'еще не было'}"
            )

        logger.info("Бот запущен и готов к работе")
        bot.infinity_polling()

    except Exception as e:
        logger.critical(f"Fatal error: {e}")
    finally:
        if 'scheduler' in locals():
            scheduler.stop()
        logger.info("Бот завершил работу")

if __name__ == "__main__":
    main()