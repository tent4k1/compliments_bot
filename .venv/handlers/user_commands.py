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
from utils.reminders_handlers import Reminders_Handlers

db = Database()
wh = Weather_Handlers()
bm = Buttons_menu()
rh = Reminders_Handlers()
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
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("telebot")
logger.setLevel(logging.DEBUG)

class DeleteState:
    def __init__(self):
        self.selected_events = {}

delete_state = DeleteState()

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
        try:
            user_id = message.from_user.id
            events = db.get_all_events(user_id=user_id)
            logger.debug(f"Events for user {user_id}: {events}")

            if isinstance(events, int):
                raise ValueError(f"Database returned integer: {events}")

            if not events:
                bot.send_message(message.chat.id, "У вас нет сохранённых событий.")
                return

            rh.send_grouped_events(chat_id=message.chat.id, events=events)

        except Exception as e:
            logger.error(f"Error in handle_view_events: {e}")
            if "chat not found" not in str(e):
                bot.send_message(message.chat.id, "❌ Ошибка при загрузке событий")

    def send_event_page(chat_id, pages, page_num):
        markup = types.InlineKeyboardMarkup()
        current_page = pages[page_num]

        text = f"📅 Ваши события ({page_num * len(current_page) + 1}-{(page_num + 1) * len(current_page)} из {sum(len(p) for p in pages)})\n"
        text += "──────────────────\n"

        for event in current_page:
            status = "🟢" if datetime.now() < event['datetime'] else "🔴"
            text += f"{status} {event['day']}.{event['month']} {event['time']} - {event['description']}\n"

        buttons = []
        if page_num > 0:
            buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"events_prev_{page_num}"))

        buttons.append(types.InlineKeyboardButton(f"{page_num + 1}/{len(pages)}", callback_data="events_page"))

        if page_num < len(pages) - 1:
            buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"events_next_{page_num}"))

        markup.row(*buttons)

        markup.row(
            types.InlineKeyboardButton("🗑 Удалить", callback_data="delete_mode"),
            types.InlineKeyboardButton("✏️ Редактировать", callback_data="events_edit")
        )

        bot.send_message(chat_id, text, reply_markup=markup)

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

    @bot.callback_query_handler(func=lambda call: call.data.startswith("del_confirm"))
    def confirm_deletion(call):
        try:
            user_id = call.from_user.id

            if user_id not in delete_state.selected_events or not delete_state.selected_events[user_id]:
                bot.answer_callback_query(call.id, "Не выбрано ни одного события", show_alert=True)
                return

            deleted_count = 0
            for event_id in list(delete_state.selected_events[user_id]):
                if db.delete_event(event_id, user_id=user_id):
                    deleted_count += 1

            del delete_state.selected_events[user_id]

            events = db.get_all_events(user_id)
            rh.send_grouped_events(
                chat_id=call.message.chat.id,
                events=events,
                message_id=call.message.message_id
            )

            bot.answer_callback_query(call.id, f"Удалено событий: {deleted_count}", show_alert=True)

        except Exception as e:
            logger.error(f"Error in confirm_deletion: {e}")
            bot.answer_callback_query(call.id, "Ошибка при удалении")

    @bot.callback_query_handler(func=lambda call: call.data == "del_cancel")
    def cancel_deletion(call):
        try:
            user_id = call.from_user.id

            if user_id in delete_state.selected_events:
                del delete_state.selected_events[user_id]

            events = db.get_all_events(user_id)
            rh.send_grouped_events(
                chat_id=call.message.chat.id,
                events=events,
                message_id=call.message.message_id
            )

            bot.answer_callback_query(call.id, "Удаление отменено")

        except Exception as e:
            logger.error(f"Error in cancel_deletion: {e}")
            bot.answer_callback_query(call.id, "Ошибка при отмене")

    @bot.callback_query_handler(func=lambda call: call.data == "delete_mode")
    def handle_delete_mode(call):
        try:
            user_id = call.from_user.id
            events = db.get_all_events(user_id=user_id)

            if not events:
                bot.answer_callback_query(call.id, "Нет событий для удаления", show_alert=True)
                return

            delete_state.selected_events[user_id] = set()

            markup = types.InlineKeyboardMarkup(row_width=1)

            for event in events:
                event_text = f"{event['day']}.{event['month']} {event.get('time', '')} - {event['event_description'][:20]}..."
                markup.add(
                    types.InlineKeyboardButton(
                        text=f"🔘 {event_text}",
                        callback_data=f"del_toggle_{event['id']}"
                    )
                )

            markup.row(
                types.InlineKeyboardButton("✅ Подтвердить удаление", callback_data="del_confirm"),
                types.InlineKeyboardButton("❌ Отменить", callback_data="del_cancel")
            )

            bot.edit_message_text(
                "🗑 Выберите события для удаления:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup
            )

        except Exception as e:
            logger.error(f"Error in enter_delete_mode: {e}")
            bot.answer_callback_query(call.id, "Ошибка при входе в режим удаления")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("del_toggle_"))
    def toggle_event_selection(call):
        try:
            user_id = call.from_user.id
            event_id = int(call.data.split("_")[2])

            if user_id not in delete_state.selected_events:
                delete_state.selected_events[user_id] = set()

            if event_id in delete_state.selected_events[user_id]:
                delete_state.selected_events[user_id].remove(event_id)
                new_prefix = "🔘"
            else:
                delete_state.selected_events[user_id].add(event_id)
                new_prefix = "✅"

            markup = types.InlineKeyboardMarkup(row_width=1)

            lines = call.message.text.split('\n')
            new_text = lines[0]

            for row in call.message.reply_markup.keyboard:
                for button in row:
                    if button.callback_data.startswith("del_toggle_"):
                        btn_event_id = int(button.callback_data.split("_")[2])
                        btn_text = button.text

                        if btn_event_id == event_id:
                            btn_text = f"{new_prefix}{btn_text[1:]}"
                        elif btn_event_id in delete_state.selected_events[user_id]:
                            btn_text = f"✅{btn_text[1:]}"
                        else:
                            btn_text = f"🔘{btn_text[1:]}"

                        markup.add(types.InlineKeyboardButton(
                            text=btn_text,
                            callback_data=button.callback_data
                        ))

            markup.row(
                types.InlineKeyboardButton("✅ Подтвердить удаление", callback_data="del_confirm"),
                types.InlineKeyboardButton("❌ Отменить", callback_data="del_cancel")
            )

            if call.message.text != new_text or str(call.message.reply_markup) != str(markup):
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=new_text,
                    reply_markup=markup
                )

            bot.answer_callback_query(call.id)

        except Exception as e:
            logger.error(f"Error in toggle_event_selection: {e}")
            bot.answer_callback_query(call.id, "Ошибка выбора события")

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

    @bot.callback_query_handler(func=lambda call: call.data.startswith(("events_prev_", "events_next_")))
    def handle_events_pagination(call):
        try:
            _, direction, page = call.data.split('_')
            page = int(page)
            new_page = page - 1 if direction == "prev" else page + 1

            events = db.get_all_events(call.from_user.id)

            send_grouped_events(
                chat_id=call.message.chat.id,
                events=events,
                page=new_page,
                message_id=call.message.message_id
            )

        except Exception as e:
            logger.error(f"Error in handle_events_pagination: {e}")
            bot.answer_callback_query(call.id, "Ошибка при переключении страницы")

    @bot.callback_query_handler(func=lambda call: call.data == "edit_mode")
    def enter_edit_mode(call):
        events = db.get_all_events(call.from_user.id)
        markup = types.InlineKeyboardMarkup()

        for event in events:
            btn_text = f"{event['day']}.{event['month']} {event.get('time', '')} - {event['event_description'][:15]}..."
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"edit_{event['id']}"))

        markup.row(
            types.InlineKeyboardButton("◀️ Назад", callback_data="cancel_edit")
        )

        bot.edit_message_text(
            "Выберите событие для редактирования:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("edit_"))
    def select_edit_field(call):
        event_id = call.data.split("_")[1]
        markup = types.InlineKeyboardMarkup()

        markup.row(
            types.InlineKeyboardButton("📅 Дата", callback_data=f"editdate_{event_id}"),
            types.InlineKeyboardButton("⏰ Время", callback_data=f"edittime_{event_id}")
        )
        markup.row(
            types.InlineKeyboardButton("📝 Текст", callback_data=f"edittext_{event_id}"),
            types.InlineKeyboardButton("🔄 Повтор", callback_data=f"editrepeat_{event_id}")
        )
        markup.row(
            types.InlineKeyboardButton("◀️ Назад", callback_data="edit_mode")
        )

        bot.edit_message_text(
            "Что хотите изменить?",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("edittext_"))
    def edit_event_text(call):
        try:
            event_id = call.data.split("_")[1]
            msg = bot.send_message(call.message.chat.id, "Введите новое описание события:")

            bot.register_next_step_handler(msg, rh.process_new_text, event_id=event_id, original_call=call)

        except Exception as e:
            logger.error(f"Error in edit_event_text: {e}")
            bot.answer_callback_query(call.id, "Ошибка при редактировании")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("page_"))
    def handle_pagination(call):
        page = int(call.data.split("_")[1])
        events = db.get_all_events(call.from_user.id)
        send_grouped_events(
            call.message.chat.id,
            events,
            page=page,
            message_id=call.message.message_id
        )

    @bot.callback_query_handler(func=lambda call: call.data == "cancel_edit")
    def handle_cancel_edit(call):
        try:
            user_id = call.from_user.id
            events = db.get_all_events(user_id=user_id)

            # Возвращаемся к основному списку событий
            rh.send_grouped_events(
                chat_id=call.message.chat.id,
                events=events,
                message_id=call.message.message_id  # Редактируем текущее сообщение
            )

            bot.answer_callback_query(call.id, "Редактирование отменено")

        except Exception as e:
            logger.error(f"Error in handle_cancel_edit: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка при отмене")