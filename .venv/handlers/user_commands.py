from telebot import TeleBot
from decorators import log_command
from keyboards.main_menu import main_menu
from database import Database

db = Database()

def setup_user_commands(bot: TeleBot, scheduler):
    @bot.message_handler(commands=['start'])
    @log_command
    def start(message):
        user = message.from_user
        # Добавляем/обновляем пользователя в БД
        db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        # Активируем подписку
        if db.set_subscription(user.id, True):
            bot.send_message(
                message.chat.id,
                "🌸 Теперь ты будешь получать случайные комплименты 3 раза в день!\n"
                "Время отправки: 8-10 утра, 13-16 дня, 19-22 вечера",
                reply_markup=main_menu()
            )
        else:
            bot.reply_to(message, "❌ Не удалось оформить подписку. Попробуйте позже.")

    @bot.message_handler(commands=['stop'])
    @log_command
    def stop(message):
        if db.set_subscription(message.chat.id, False):
            bot.send_message(
                message.chat.id,
                "😢 Ты больше не будешь получать комплименты...",
                reply_markup=main_menu()
            )
        else:
            bot.reply_to(message, "❌ Не удалось отписаться. Попробуйте позже.")

    @bot.message_handler(func=lambda msg: msg.text == '💝 Получить комплимент')
    def send_random_compliment(message):
        compliment = db.get_random_compliment()
        if compliment:
            compliment_id, text = compliment
            bot.send_message(message.chat.id, f"✨ {text}")
            db.record_sent_compliment(message.chat.id, compliment_id)
        else:
            bot.reply_to(message, "😔 Нет доступных комплиментов. Попробуйте позже.")

    @bot.message_handler(func=lambda msg: msg.text == '✅ Подписаться')
    def subscribe(message):
        if db.set_subscription(message.chat.id, True):
            bot.reply_to(message, "✅ Вы подписались на ежедневные комплименты!")
        else:
            bot.reply_to(message, "❌ Не удалось подписаться. Попробуйте позже.")

    @bot.message_handler(func=lambda msg: msg.text == '❌ Отписаться')
    def unsubscribe(message):
        if db.set_subscription(message.chat.id, False):
            bot.reply_to(message, "❌ Вы отписались от рассылки")
        else:
            bot.reply_to(message, "❌ Не удалось отписаться. Попробуйте позже.")

    @bot.message_handler(func=lambda msg: msg.text == '📊 Статистика')
    @log_command
    def stats_user(message):
        stats = db.get_stats()
        try:
            stats_msg = (
                f"📊 Статистика бота:\n"
                f"• Всего пользователей: {stats.get('total_users', 0)}\n"
                f"• Подписано: {stats.get('subscribed_users', 0)}\n"
                f"• Всего комплиментов: {stats.get('total_compliments', 0)}\n"
                f"• Отправлено сегодня: {stats.get('sent_today', 0)}"
            )
            bot.reply_to(message, stats_msg)
        except Exception as e:
            logging.error(f"Failed to send stats: {e}")
            bot.reply_to(message, "❌ Не удалось получить статистику. Попробуйте позже.")

    @bot.message_handler(func=lambda msg: msg.text == '✅ Проверить подписку')
    @log_command
    def status(message):
        is_subscribed = db.is_user_subscribed(message.chat.id)
        if is_subscribed is None:
            bot.reply_to(message, "❌ Ваш статус не определен. Попробуйте /start")
        elif is_subscribed:
            bot.reply_to(message, "✅ Вы подписаны на рассылку комплиментов!")
        else:
            bot.reply_to(message, "❌ Вы не подписаны на рассылку.")