from telebot import TeleBot
from decorators import admin_only, log_command
from database import Database


def setup_admin_commands(bot: TeleBot, db: Database):
    """Настройка административных команд с доступом к базе данных"""

    @bot.message_handler(commands=['stats'])
    @admin_only
    @log_command
    def stats(message):
        """Отправка подробной статистики админу"""
        try:
            stats_data = db.get_detailed_stats()

            stats_msg = (
                "📊 *Детальная статистика бота:*\n"
                f"• Всего пользователей: `{stats_data['total_users']}`\n"
                f"• Активных подписок: `{stats_data['active_subscriptions']}`\n"
                f"• Новых за 24 часа: `{stats_data['new_users_24h']}`\n"
                f"• Всего комплиментов: `{stats_data['total_compliments']}`\n"
                f"• Активных комплиментов: `{stats_data['active_compliments']}`\n"
                f"• Отправлено сегодня: `{stats_data['sent_today']}`\n"
                f"• Последняя отправка: `{stats_data['last_sent_time'] or 'еще не было'}`"
            )

            bot.send_message(message.chat.id, stats_msg, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"Failed to send stats: {e}")
            bot.reply_to(message, "❌ Не удалось получить статистику. Попробуйте позже.")

    @bot.message_handler(commands=['add'])
    @admin_only
    @log_command
    def add_compliment(message):
        """Добавить новый комплимент в базу данных"""
        text = message.text.replace('/add', '').strip()
        if text:
            if db.add_compliment(text):
                bot.reply_to(message, "✅ Комплимент добавлен в базу данных!")
            else:
                bot.reply_to(message, "❌ Не удалось добавить комплимент (возможно, уже существует)")

    @bot.message_handler(commands=['backup'])
    @admin_only
    @log_command
    def backup_db(message):
        """Создать резервную копию базы данных"""
        backup_path = db.backup_database()
        if backup_path:
            try:
                with open(backup_path, 'rb') as f:
                    bot.send_document(
                        message.chat.id,
                        f,
                        caption=f"✅ Резервная копия создана: {backup_path}"
                    )
            except Exception as e:
                bot.reply_to(message, f"❌ Не удалось отправить backup: {e}")
        else:
            bot.reply_to(message, "❌ Не удалось создать резервную копию")

    @bot.message_handler(commands=['userinfo'])
    @admin_only
    @log_command
    def user_info(message):
        """Получить информацию о пользователе"""
        try:
            # Ожидаем ввод user_id после команды
            msg = bot.reply_to(message, "Введите ID пользователя:")
            bot.register_next_step_handler(msg, process_user_id_step)
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка: {e}")

    def process_user_id_step(message):
        try:
            user_id = int(message.text)
            user_info = db.get_user_info(user_id)
            if user_info:
                username, first_name, last_name, sub_date, last_active = user_info
                bot.reply_to(
                    message,
                    f"👤 Информация о пользователе {user_id}:\n"
                    f"• Username: @{username or 'нет'}\n"
                    f"• Имя: {first_name or 'нет'} {last_name or ''}\n"
                    f"• Дата регистрации: {sub_date}\n"
                    f"• Последняя активность: {last_active or 'неизвестно'}"
                )
            else:
                bot.reply_to(message, "Пользователь не найден в базе данных")
        except ValueError:
            bot.reply_to(message, "Некорректный ID пользователя")
        except Exception as e:
            bot.reply_to(message, f"Ошибка при получении данных: {e}")

    return bot