import telebot
import logging
from threading import Thread
import time
from config import TOKEN
from database import Database
from scheduler import ComplimentScheduler
from handlers.user_commands import setup_user_commands
from handlers.admin_commands import setup_admin_commands

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

def run_health_check(scheduler):
    """Фоновая проверка состояния бота"""
    while True:
        try:
            status = scheduler.check_working()
            logging.info(
                f"Health check: {status['users_count']} users, "
                f"{status['compliments_available']} compliments available"
            )
            time.sleep(300)
        except Exception as e:
            logging.error(f"Health check failed: {e}")
            time.sleep(60)

def main():
    try:
        # Инициализация бота
        bot = telebot.TeleBot(TOKEN)
        db = Database()
        scheduler = ComplimentScheduler(bot, db)

        # Восстановление подписок и уведомление пользователей
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
                logging.error(f"Failed to notify user {user_id}: {e}")
                db.set_subscription(user_id, False)

        logging.info(f"Restored {restored_users} subscriptions")

        # Настройка обработчиков команд
        setup_user_commands(bot, db)
        setup_admin_commands(bot, db)

        # Запуск планировщика комплиментов
        scheduler.start()

        # Запуск фоновой проверки здоровья
        health_thread = Thread(target=run_health_check, args=(scheduler,), daemon=True)
        health_thread.start()

        # Команда для проверки статуса
        @bot.message_handler(commands=['status'])
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

        logging.info("Бот запущен и готов к работе")
        bot.infinity_polling()

    except Exception as e:
        logging.critical(f"Fatal error: {e}")
    finally:
        if 'scheduler' in locals():
            scheduler.stop()
        logging.info("Бот завершил работу")

if __name__ == "__main__":
    main()