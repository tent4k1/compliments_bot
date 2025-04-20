from telebot import TeleBot
from decorators import admin_only, log_command
from database import Database

def setup_admin_commands(bot: TeleBot, db: Database):
    user_wish_selections = {}
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
            msg = bot.reply_to(message, "Введите ID пользователя:")
            bot.register_next_step_handler(msg, process_user_id_step)
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка: {e}")

    from telebot import types
    from config import ADMIN_ID, MIUS_ID

    def get_wishlist_keyboard():
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        btn_add = types.KeyboardButton('➕ Добавить желание')
        btn_my = types.KeyboardButton('📋 Мои желания')
        btn_partner = types.KeyboardButton('🎁 Желания партнера')
        btn_fulfill = types.KeyboardButton('✅ Отметить исполненным')
        btn_delete = types.KeyboardButton('❌ Удалить желание')
        btn_back = types.KeyboardButton('🔙 Назад')
        markup.add(btn_add, btn_my, btn_partner, btn_fulfill, btn_delete, btn_back)
        return markup

    # Обработчик кнопки "Вишлист" в главном меню
    @bot.message_handler(func=lambda msg: msg.text == '📋 Вишлист')
    @admin_only
    @log_command
    def wishlist_menu(message):
        bot.send_message(
            message.chat.id,
            "📋 Управление вишлистом:",
            reply_markup=get_wishlist_keyboard()
        )

    # Обработчики кнопок вишлиста
    @bot.message_handler(func=lambda msg: msg.text == '➕ Добавить желание')
    @admin_only
    @log_command
    def handle_add_wish(message):
        msg = bot.send_message(message.chat.id, "Напишите ваше желание:")
        bot.register_next_step_handler(msg, process_add_wish)

    def process_add_wish(message):
        if message.text == '🔙 Назад':
            handle_back(message)
            return

        if db.add_wish(message.chat.id, message.text):
            bot.send_message(
                message.chat.id,
                "✅ Желание добавлено!",
                reply_markup=get_wishlist_keyboard()
            )
        else:
            bot.send_message(
                message.chat.id,
                "❌ Ошибка при добавлении",
                reply_markup=get_wishlist_keyboard()
            )

    @bot.message_handler(func=lambda msg: msg.text == '📋 Мои желания')
    @admin_only
    @log_command
    def show_my_wishes_handler(message):
        wishes = db.get_user_wishes(message.chat.id)
        if not wishes:
            bot.send_message(message.chat.id, "У вас пока нет желаний", reply_markup=get_wishlist_keyboard())
            return

        response = "📝 Ваши желания:\n\n"
        for wish_id, text, fulfilled in wishes:
            status = "✅ Исполнено" if fulfilled else "❌ Не исполнено"
            response += f"{wish_id}. {text} - {status}\n"

        bot.send_message(
            message.chat.id,
            response,
            reply_markup=get_wishlist_keyboard())

    @bot.message_handler(func=lambda msg: msg.text == '🎁 Желания партнера')
    @admin_only
    @log_command
    def show_partner_wishes_handler(message):
        wishes = db.get_partner_wishes(message.chat.id)
        if not wishes:
            bot.send_message(message.chat.id, "У партнера пока нет желаний", reply_markup=get_wishlist_keyboard())
            return

        response = "🎁 Желания партнера:\n\n"
        for wish_id, text in wishes:
            response += f"{wish_id}. {text}\n"

        bot.send_message(message.chat.id, response, reply_markup=get_wishlist_keyboard())

    @bot.message_handler(func=lambda msg: msg.text == '✅ Отметить исполненным')
    @admin_only
    @log_command
    def fulfill_wish_handler(message):
        msg = bot.reply_to(message, "Введите номер желания для отметки:")
        bot.register_next_step_handler(msg, process_fulfill)

    def process_fulfill(message):
        if message.text == '🔙 Назад':
            handle_back(message)
            return

        try:
            wish_id = int(message.text)
            if db.mark_fulfilled(wish_id):
                bot.send_message(
                    message.chat.id,
                    "🎉 Желание отмечено исполненным!",
                    reply_markup=get_wishlist_keyboard()
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "❌ Не удалось отметить желание",
                    reply_markup=get_wishlist_keyboard()
                )
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ Нужно ввести число",
                reply_markup=get_wishlist_keyboard()
            )

    @bot.message_handler(func=lambda msg: msg.text == '❌ Удалить желание')
    @admin_only
    @log_command
    def handle_delete_wish(message):
        # Получение списка желаний пользователя
        wishes = db.get_user_wishes(message.chat.id)
        if not wishes:
            bot.send_message(
                message.chat.id,
                "У вас пока нет желаний для удаления",
                reply_markup=get_wishlist_keyboard()
            )
            return

        # Сохранение списка желаний для этого пользователя
        user_wish_selections[message.chat.id] = wishes

        # Создание клавиатуры с кнопками
        markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        for wish in wishes:
            wish_id, text, _ = wish
            btn_text = f"❌ {wish_id}: {text[:20]}..." if len(text) > 20 else f"❌ {wish_id}: {text}"
            markup.add(types.KeyboardButton(btn_text))
        markup.add(types.KeyboardButton('🔙 Отмена'))

        bot.send_message(
            message.chat.id,
            "Выберите желание для удаления:",
            reply_markup=markup
        )

    @bot.message_handler(func=lambda msg: msg.text.startswith('❌ '))
    def process_delete_wish(message):
        try:
            # Получение сохраненного списка желаний
            wishes = user_wish_selections.get(message.chat.id, [])
            if not wishes:
                raise ValueError("Нет сохраненных желаний")

            # Извлечение ID из текста
            selected_text = message.text[2:]
            wish_id = int(selected_text.split(':')[0].strip())

            # Проверяка, что желание существует
            if not any(wish[0] == wish_id for wish in wishes):
                raise ValueError("Неверный ID желания")

            # Удаление желание
            if db.delete_wish(wish_id, message.chat.id):
                bot.send_message(
                    message.chat.id,
                    "✅ Желание успешно удалено!",
                    reply_markup=get_wishlist_keyboard()
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "❌ Не удалось удалить желание или оно вам не принадлежит",
                    reply_markup=get_wishlist_keyboard()
                )

            # Очистка временного хранилища
            user_wish_selections.pop(message.chat.id, None)

        except Exception as e:
            bot.send_message(
                message.chat.id,
                "❌ Ошибка при удалении. Пожалуйста, попробуйте снова.",
                reply_markup=get_wishlist_keyboard()
            )
            user_wish_selections.pop(message.chat.id, None)

    @bot.message_handler(func=lambda msg: msg.text == '🔙 Отмена')
    def handle_cancel_delete(message):
        bot.send_message(
            message.chat.id,
            "Управление вишлистом:",
            reply_markup=get_wishlist_keyboard()
        )
        user_wish_selections.pop(message.chat.id, None)

    @bot.message_handler(func=lambda msg: msg.text == '🔙 Назад')
    @admin_only
    @log_command
    def back_handler(message):
        from handlers.user_commands import main_menu
        bot.send_message(
            message.chat.id,
            "Главное меню:",
            reply_markup=main_menu()
        )

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