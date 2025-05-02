import os
import requests
import logging
import calendar

from datetime import datetime
from sched import scheduler
from telebot import TeleBot, types
from decorators import log_command
from keyboards.main_menu import Buttons_menu
from database import Database
from config import WEATHER, DEFAULT_CITY, TOKEN
from utils.weather_handlers import Weather_Handlers
from utils.scheduler import ComplimentScheduler

db = Database()
wh = Weather_Handlers()
bm = Buttons_menu()
bot = TeleBot(TOKEN)
scheduler = ComplimentScheduler(bot, db)

user_event_data = { }
event_data_template = {
    'year': 2025,
    'month': None,
    'day': None,
    'time': None,
    'event_description': None,
    'all_day': 0,
    'repeat': 0
}
event_data = {
    'year': 2025,
    'month': None,
    'day': None,
    'time': None,
    'event_description': None,
    'all_day': 0,
    'repeat': 0
}
logging.basicConfig(level=logging.DEBUG)

# Включаем логирование для бота
logger = logging.getLogger("telebot")
logger.setLevel(logging.DEBUG)

def setup_user_commands(bot: TeleBot):
    @bot.message_handler(commands=['start'])
    @log_command
    # ========== Main ==========
    def start(message):
        user = message.from_user
        db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

        if db.set_subscription(user.id, True):
            bot.send_message(
                message.chat.id,
                "🌸 Теперь ты будешь получать случайные комплименты 3 раза в день!\n"
                "Время отправки: 8-10 утра, 13-16 дня, 19-22 вечера",
                reply_markup = bm.main_menu()
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
                reply_markup = bm.main_menu()
            )
        else:
            bot.reply_to(message, "❌ Не удалось отписаться. Попробуйте позже.")

    @bot.message_handler(func=lambda message: message.text == "🔙 Назад")
    def handle_back(message):
        bot.send_message(message.chat.id, "Вы вернулись в главное меню.", reply_markup=bm.main_menu())

    # ========== Compliments ==========
    @bot.message_handler(func=lambda msg: msg.text == '💝 Получить комплимент')
    def send_random_compliment(message):
        compliment = db.get_random_compliment()
        if compliment:
            compliment_id, text = compliment
            bot.send_message(message.chat.id, f"✨ {text}")
            db.record_sent_compliment(message.chat.id, compliment_id)
        else:
            bot.reply_to(message, "😔 Нет доступных комплиментов. Попробуйте позже.")

    # ========== Subscribe ==========
    @bot.message_handler(func=lambda msg: msg.text == '☑ Подписка')
    @log_command
    def subscribe_menu(message):
        bot.send_message(
            message.chat.id,
            "☑ Управление подпиской:",
            reply_markup = bm.get_subscribe_keyboard()
        )

    @bot.message_handler(func=lambda msg: msg.text == '✅ Подписаться')
    @log_command
    def subscribe(message):
        if db.set_subscription(message.chat.id, True):
            bot.reply_to(message, "✅ Вы подписались на ежедневные комплименты!")
        else:
            bot.reply_to(message, "❌ Не удалось подписаться. Попробуйте позже.")

    @bot.message_handler(func=lambda msg: msg.text == '❌ Отписаться')
    @log_command
    def unsubscribe(message):
        if db.set_subscription(message.chat.id, False):
            bot.reply_to(message, "❌ Вы отписались от рассылки")
        else:
            bot.reply_to(message, "❌ Не удалось отписаться. Попробуйте позже.")

    @bot.message_handler(func=lambda msg: msg.text == '❓ Проверить подписку')
    @log_command
    def status(message):
        is_subscribed = db.is_user_subscribed(message.chat.id)
        if is_subscribed is None:
            bot.reply_to(message, "❌ Ваш статус не определен. Попробуйте /start")
        elif is_subscribed:
            bot.reply_to(message, "✅ Вы подписаны на рассылку комплиментов!")
        else:
            bot.reply_to(message, "❌ Вы не подписаны на рассылку.")

    # ========== Stats ==========
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

    # ========== Weather ==========
    @bot.message_handler(func=lambda msg: msg.text == '🌡 Погода')
    @log_command
    def weather_menu(message):
        bot.send_message(
            message.chat.id,
            "⌨ Выбор города:",
            reply_markup = bm.get_weather_keyboard()
        )

    @bot.message_handler(func=lambda msg: msg.text in ['Москва', 'Подольск',
                                                       'Ефремов', 'Дубай'] or msg.text == '🌍 Ввести другой город')
    @log_command
    def handle_city_selection(message):
        if message.text == '🌍 Ввести другой город':
            msg = bot.reply_to(message, "Введите название города:", reply_markup=types.ForceReply())
            bot.register_next_step_handler(msg, process_weather_request)
        else:
            process_weather_request(message)

    def process_weather_request(message):
        city = message.text
        try:
            weather_data = wh.get_weather_data(city)
            response = wh.format_weather_response(weather_data)
            bot.send_message(
                message.chat.id,
                response,
                reply_markup = bm.get_weather_keyboard(),
                parse_mode='HTML'
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return "Город не найден"
            elif e.response.status_code == 401:
                return "Ошибка API ключа"
            else:
                return "Ошибка сервера"

    @bot.message_handler(func=lambda msg: msg.text == '📈 Прогноз погоды')
    @log_command
    def handle_weather_command(message):
        try:
            forecast = wh.get_daily_forecast(DEFAULT_CITY)
            bot.send_message(
                message.chat.id,
                forecast,
                parse_mode='HTML'
            )
        except Exception as e:
            bot.reply_to(
                message,
                f"❌ Ошибка при получении погоды: {str(e)}",
                parse_mode='HTML'
            )

    @bot.message_handler(func=lambda msg: msg.text == '✔ Установить город по умолчания')
    def set_weather_city(message):
        try:
            city = message.text.split(maxsplit=1)[1]
            bot.reply_to(message, f"🌆 Город для погоды установлен: {city}")
        except IndexError:
            bot.reply_to(message, "Ошибка")

    # ========== Reminders ==========
    @bot.message_handler(func=lambda message: message.text == "📅 Календарь")
    def handle_calendar_menu(message):
        bot.send_message(message.chat.id, "🗓 Меню календаря:", reply_markup=bm.get_calendar_menu())

    @bot.message_handler(func=lambda message: message.text == "📆 Добавить событие")
    def handle_add_event(message):
        user_id = message.chat.id
        if user_id not in user_event_data:
            user_event_data[user_id] = {}
        bot.send_message(user_id, "Выберите год:", reply_markup=bm.get_year_menu())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("year_"))
    def handle_year_selection(call):
        user_id = call.message.chat.id
        try:
            selected_year = int(call.data.split("_")[1])
            user_event_data[user_id]['year'] = selected_year
            bot.edit_message_text(
                f"Вы выбрали {selected_year} год. Теперь выберите месяц:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=bm.get_month_menu()
            )
        except Exception as e:
            logging.error(f"Error in year selection: {e}")
            bot.answer_callback_query(call.id, "Ошибка выбора года")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('month_'))
    def handle_month_selection(call):
        user_id = call.message.chat.id
        try:
            selected_month = int(call.data.split('_')[1])
            user_event_data[user_id]['month'] = selected_month
            year = user_event_data[user_id].get('year', datetime.now().year)
            bot.edit_message_text(
                f"Вы выбрали месяц: {selected_month}. Теперь выберите день:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=bm.get_day_menu(selected_month, year)
            )
        except Exception as e:
            logging.error(f"Error in month selection: {e}")
            bot.answer_callback_query(call.id, "Ошибка выбора месяца")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('day_'))
    def handle_day_selection(call):
        user_id = call.message.chat.id
        try:
            selected_day = int(call.data.split('_')[1])
            user_event_data[user_id]['day'] = selected_day
            bot.edit_message_text(
                f"Вы выбрали день: {selected_day}. Теперь выберите время:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=bm.get_time_menu()
            )
        except Exception as e:
            logging.error(f"Error in day selection: {e}")
            bot.answer_callback_query(call.id, "Ошибка выбора дня")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('time_'))
    def handle_time_selection(call):
        user_id = call.message.chat.id
        try:
            selected = call.data.split('_')[1]

            if selected == 'allday':
                user_event_data[user_id]['time'] = '08:00'
                user_event_data[user_id]['all_day'] = 1
                bot.edit_message_text(
                    "Вы выбрали: весь день. Хотите, чтобы событие повторялось?",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=bm.get_reminder_offset_menu()
                )
            elif selected == 'custom':
                user_event_data[user_id]['awaiting_time'] = True
                bot.send_message(user_id, "Введите время в формате ЧЧ:ММ (например, 09:30):")
            else:
                user_event_data[user_id]['time'] = selected
                user_event_data[user_id]['all_day'] = 0
                bot.edit_message_text(
                    f"Вы выбрали время: {selected}. Теперь выберите, за сколько времени напомнить:",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=bm.get_reminder_offset_menu()
                )
        except Exception as e:
            logging.error(f"Error in time selection: {e}")
            bot.answer_callback_query(call.id, "Ошибка выбора времени")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('reminder_'))
    def handle_reminder_offset_selection(call):
        user_id = call.message.chat.id
        try:
            offset = call.data.split('_')[1]
            if offset == 'none':
                user_event_data[user_id]['reminder_offset'] = 0
            else:
                user_event_data[user_id]['reminder_offset'] = int(offset)

            bot.edit_message_text(
                "Хотите, чтобы событие повторялось ежедневно или было одноразовым?",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=bm.get_repeat_menu()
            )
        except Exception as e:
            logging.error(f"Error in reminder offset selection: {e}")
            bot.answer_callback_query(call.id, "Ошибка выбора напоминания")

    @bot.message_handler(func=lambda message: message.text == "📋 Мои события")
    def handle_view_events(message):
        user_id = message.from_user.id
        try:
            events = db.get_all_events(user_id=user_id)

            if not events:
                bot.send_message(message.chat.id, "У вас нет сохранённых событий.")
                return

            for event in events:
                try:
                    event_id = event['id']
                    year = event['year']
                    month = event['month']
                    day = event['day']
                    time = event['time'] if event['time'] else "00:00"
                    description = event['event_description'] if event['event_description'] else "Без описания"
                    repeat = event['repeat']
                    reminder_offset = event.get('reminder_offset', 0)

                    date_parts = []
                    if year and str(year).isdigit():
                        date_parts.append(str(int(year)))
                    if month and str(month).isdigit():
                        date_parts.append(f"{int(month):02d}")
                    if day and str(day).isdigit():
                        date_parts.append(f"{int(day):02d}")

                    date_str = "-".join(date_parts) if date_parts else "❓ Дата не указана"
                    if repeat:
                        date_str = "⏰ Повторяется ежедневно"

                    text = f"📅 ID: {event_id} | {date_str} в {time}\n📝 {description}"
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{event_id}"))

                    bot.send_message(message.chat.id, text, reply_markup=markup)
                except Exception as e:
                    logger.error(f"Error formatting event {event}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error getting events for user {user_id}: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка при загрузке событий")

    @bot.callback_query_handler(func=lambda call: call.data in ["repeat_daily", "repeat_once"])
    def handle_repeat_selection(call):
        user_id = call.message.chat.id
        try:
            user_event_data[user_id]['repeat'] = 1 if call.data == "repeat_daily" else 0
            bot.edit_message_text(
                "✏️ Введите описание события:",
                call.message.chat.id,
                call.message.message_id
            )
        except Exception as e:
            logging.error(f"Error in repeat selection: {e}")
            bot.answer_callback_query(call.id, "Ошибка выбора повторения")

    @bot.message_handler(func=lambda message: user_event_data.get(message.chat.id, {}).get('repeat') is not None)
    def handle_event_description(message):
        user_id = message.chat.id
        event_data = user_event_data.get(user_id, {})

        required_fields = ['year', 'month', 'day', 'time']
        if not all(field in event_data for field in required_fields):
            missing = [f for f in required_fields if f not in event_data]
            bot.send_message(user_id, f"⛔ Не хватает данных: {', '.join(missing)}")
            return

        event_description = message.text.strip()
        try:
            event_id = db.save_event(
                user_id=user_id,
                year=event_data['year'],
                month=event_data['month'],
                day=event_data['day'],
                time=event_data['time'],
                event_description=event_description,
                all_day=event_data.get('all_day', 0),
                repeat=event_data.get('repeat', 0),
                reminder_offset=event_data.get('reminder_offset', 0)
            )

            if not event_id:
                bot.send_message(user_id, "❌ Ошибка сохранения события в БД")
                return

            event_data_for_scheduler = {
                'id': event_id,
                'year': event_data['year'],
                'month': event_data['month'],
                'day': event_data['day'],
                'time': event_data['time'],
                'event_description': event_description,
                'repeat': event_data.get('repeat', 0),
                'reminder_offset': event_data.get('reminder_offset', 0)
            }

            if scheduler.schedule_event_reminder(event_data_for_scheduler, user_id):
                bot.send_message(user_id, "✅ Событие сохранено и напоминание установлено!")
            else:
                bot.send_message(user_id, "⚠️ Событие сохранено, но не удалось установить напоминание")

            user_event_data.pop(user_id, None)

        except Exception as e:
            logger.error(f"System error in handle_event_description: {e}")
            bot.send_message(user_id, "❌ Произошла системная ошибка при обработке события")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
    def handle_delete_event(call):
        try:
            event_id = int(call.data.split("_")[1])
            if db.delete_event(event_id):
                scheduler.cancel_event_reminder(event_id)
                bot.answer_callback_query(call.id, "Событие удалено ✅")
                bot.edit_message_text(
                    f"✅ Событие с ID {event_id} удалено.",
                    call.message.chat.id,
                    call.message.message_id
                )
            else:
                bot.answer_callback_query(call.id, "Событие не найдено ❌")
        except Exception as e:
            logging.error(f"Error deleting event: {e}")
            bot.answer_callback_query(call.id, "Ошибка удаления ❌")

    @bot.message_handler(func=lambda message: user_event_data.get(message.chat.id, {}).get('awaiting_time'))
    def process_custom_time(message):
        user_id = message.chat.id
        time_input = message.text.strip()

        try:
            datetime.strptime(time_input, "%H:%M")
            user_event_data[user_id]['time'] = time_input
            user_event_data[user_id]['awaiting_time'] = False

            bot.send_message(
                user_id,
                f"Вы установили время: {time_input}. Теперь выберите, за сколько времени напомнить:",
                reply_markup=bm.get_reminder_offset_menu()
            )
        except ValueError:
            bot.send_message(user_id, "⛔ Неверный формат времени. Пожалуйста, введите в формате ЧЧ:ММ.")