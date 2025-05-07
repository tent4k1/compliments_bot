import os
import requests
import logging
import calendar

from datetime import datetime
from telebot import TeleBot, types
from utils.decorators import log_command
from database import Database
from config import WEATHER, DEFAULT_CITY, TOKEN

class UserCommands:
    def __init__(self, bot, db, bm, wh, rh, lh, scheduler):
        self.bot = bot
        self.db = db
        self.bm = bm
        self.wh = wh
        self.rh = rh
        self.lh = lh
        self.scheduler = scheduler
        self.logger = logging.getLogger(__name__)
        self.user_event_data = {}
        self.event_data_template = {
            'year': 2025,
            'month': None,
            'day': None,
            'time': None,
            'event_description': None,
            'all_day': 0,
            'repeat': 0
        }
        self._register_handlers()

    def _register_handlers(self):
        # ========== Main ==========
        @self.bot.message_handler(commands=['start'])
        @log_command
        def start(message):
            user = message.from_user
            self.db.add_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )

            if self.db.set_subscription(user.id, True):
                self.bot.send_message(
                    message.chat.id,
                    "🌸 Теперь ты будешь получать случайные комплименты 3 раза в день!\n"
                    "Время отправки: 8-10 утра, 13-16 дня, 19-22 вечера",
                    reply_markup=self.bm.main_menu()
                )
            else:
                self.bot.reply_to(message, "❌ Не удалось оформить подписку. Попробуйте позже.")

        @self.bot.message_handler(commands=['stop'])
        @log_command
        def stop(message):
            if self.db.set_subscription(message.chat.id, False):
                self.bot.send_message(
                    message.chat.id,
                    "😢 Ты больше не будешь получать комплименты...",
                    reply_markup=self.bm.main_menu()
                )
            else:
                self.bot.reply_to(message, "❌ Не удалось отписаться. Попробуйте позже.")

        @self.bot.message_handler(func=lambda message: message.text == "🔙 Назад")
        def handle_back(message):
            self.bot.send_message(message.chat.id, "Вы вернулись в главное меню.", reply_markup=self.bm.main_menu())

        # ========== Compliments ==========
        @self.bot.message_handler(func=lambda msg: msg.text == '💝 Получить комплимент')
        def send_random_compliment(message):
            user_id = message.chat.id
            compliment = self.db.get_random_compliment(user_id)
            if compliment:
                compliment_id, text = compliment
                self.bot.send_message(message.chat.id, f"✨ {text}")
                self.db.record_sent_compliment(message.chat.id, compliment_id)
            else:
                self.bot.reply_to(message, "😔 Нет доступных комплиментов. Попробуйте позже.")

        # ========== Subscribe ==========
        @self.bot.message_handler(func=lambda msg: msg.text == '☑ Подписка')
        @log_command
        def subscribe_menu(message):
            self.bot.send_message(
                message.chat.id,
                "☑ Управление подпиской:",
                reply_markup=self.bm.get_subscribe_keyboard()
            )

        @self.bot.message_handler(func=lambda msg: msg.text == '✅ Подписаться')
        @log_command
        def subscribe(message):
            if self.db.set_subscription(message.chat.id, True):
                self.bot.reply_to(message, "✅ Вы подписались на ежедневные комплименты!")
            else:
                self.bot.reply_to(message, "❌ Не удалось подписаться. Попробуйте позже.")

        @self.bot.message_handler(func=lambda msg: msg.text == '❌ Отписаться')
        @log_command
        def unsubscribe(message):
            if self.db.set_subscription(message.chat.id, False):
                self.bot.reply_to(message, "❌ Вы отписались от рассылки")
            else:
                self.bot.reply_to(message, "❌ Не удалось отписаться. Попробуйте позже.")

        @self.bot.message_handler(func=lambda msg: msg.text == '❓ Проверить подписку')
        @log_command
        def status(message):
            is_subscribed = self.db.is_user_subscribed(message.chat.id)
            if is_subscribed is None:
                self.bot.reply_to(message, "❌ Ваш статус не определен. Попробуйте /start")
            elif is_subscribed:
                self.bot.reply_to(message, "✅ Вы подписаны на рассылку комплиментов!")
            else:
                self.bot.reply_to(message, "❌ Вы не подписаны на рассылку.")

        # ========== Stats ==========
        @self.bot.message_handler(func=lambda msg: msg.text == '📊 Статистика')
        @log_command
        def stats_user(message):
            stats = self.db.get_stats()
            try:
                stats_msg = (
                    f"📊 Статистика бота:\n"
                    f"• Всего пользователей: {stats.get('total_users', 0)}\n"
                    f"• Подписано: {stats.get('subscribed_users', 0)}\n"
                    f"• Всего комплиментов: {stats.get('total_compliments', 0)}\n"
                    f"• Отправлено сегодня: {stats.get('sent_today', 0)}"
                )
                self.bot.reply_to(message, stats_msg)
            except Exception as e:
                self.logger.error(f"Failed to send stats: {e}")
                self.bot.reply_to(message, "❌ Не удалось получить статистику. Попробуйте позже.")

        # ========== Weather ==========
        @self.bot.message_handler(func=lambda msg: msg.text == '🌡 Погода')
        @log_command
        def weather_menu(message):
            self.bot.send_message(
                message.chat.id,
                "⌨ Выбор города:",
                reply_markup=self.bm.get_weather_keyboard()
            )

        @self.bot.message_handler(func=lambda msg: msg.text in ['Москва', 'Подольск',
                                                           'Ефремов', 'Дубай'] or msg.text == '🌍 Ввести другой город')
        @log_command
        def handle_city_selection(message):
            if message.text == '🌍 Ввести другой город':
                msg = self.bot.reply_to(message, "Введите название города:", reply_markup=types.ForceReply())
                self.bot.register_next_step_handler(msg, process_weather_request)
            else:
                process_weather_request(message)

        def process_weather_request(message):
            city = message.text
            try:
                weather_data = self.wh.get_weather_data(city)
                response = self.wh.format_weather_response(weather_data)
                self.bot.send_message(
                    message.chat.id,
                    response,
                    reply_markup=self.bm.get_weather_keyboard(),
                    parse_mode='HTML'
                )
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    return "Город не найден"
                elif e.response.status_code == 401:
                    return "Ошибка API ключа"
                else:
                    return "Ошибка сервера"

        @self.bot.message_handler(func=lambda msg: msg.text == '📈 Прогноз погоды')
        @log_command
        def handle_weather_command(message):
            try:
                forecast = self.wh.get_daily_forecast(DEFAULT_CITY)
                self.bot.send_message(
                    message.chat.id,
                    forecast,
                    parse_mode='HTML'
                )
            except Exception as e:
                self.bot.reply_to(
                    message,
                    f"❌ Ошибка при получении погоды: {str(e)}",
                    parse_mode='HTML'
                )

        @self.bot.message_handler(func=lambda msg: msg.text == '✔ Установить город по умолчания')
        def set_weather_city(message):
            try:
                city = message.text.split(maxsplit=1)[1]
                self.bot.reply_to(message, f"🌆 Город для погоды установлен: {city}")
            except IndexError:
                self.bot.reply_to(message, "Ошибка")

        # ========== Reminders ==========
        @self.bot.message_handler(func=lambda message: message.text == "📅 Календарь")
        def handle_calendar_menu(message):
            self.bot.send_message(message.chat.id, "🗓 Меню календаря:", reply_markup=self.bm.get_calendar_menu())

        @self.bot.message_handler(func=lambda message: message.text == "📆 Добавить событие")
        def handle_add_event(message):
            markup = self.rh.start_event_creation(message.chat.id)
            self.bot.send_message(message.chat.id, "Выберите год:", reply_markup=markup)

        @self.bot.message_handler(func=lambda message: message.text == "📋 Мои события")
        def handle_view_events(message):
            try:
                user_id = message.from_user.id
                events = self.db.get_all_events(user_id=user_id)

                if isinstance(events, int):
                    raise ValueError(f"Database returned integer: {events}")

                if not events:
                    self.bot.send_message(message.chat.id, "У вас нет сохранённых событий.")
                    return

                self.rh.send_grouped_events(chat_id=message.chat.id, events=events)

            except Exception as e:
                self.logger.error(f"Error in handle_view_events: {e}")
                if "chat not found" not in str(e):
                    self.bot.send_message(message.chat.id, "❌ Ошибка при загрузке событий")

        # ========== Lists ==========
        @self.bot.message_handler(func=lambda message: message.text == "📝 Списки")
        def handle_list_options(message):
            try:
                self.bot.send_message(
                    message.chat.id,
                    "⌨ Выбор города:",
                    reply_markup=self.bm.get_lists_menu()
                )
            except Exception as e:
                self.logger.warning(f"[handle_list_options] Ошибка при вызове клавиатуры: {e}")

        @self.bot.message_handler(func=lambda message: message.text == "👥 Мой партнёр")
        def handle_my_partner_button(message):
            try:
                user_id = message.from_user.id
                partner_id = self.db.get_partner(user_id)
                if partner_id:
                    partner = self.bot.get_chat(partner_id)
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("❌ Удалить партнёра", callback_data="delete_partner_confirm"))

                    self.bot.send_message(
                        user_id,
                        f"🤝 Ваш партнёр: @{partner.username or partner_id}",
                        reply_markup=markup
                    )
                else:
                    self.bot.send_message(user_id, "❗ У вас пока нет подтверждённого партнёра.")
            except Exception as e:
                self.logger.warning(f"[handle_my_partner_button] Ошибка при получении партнера: {e}")

        @self.bot.message_handler(func=lambda message: message.text == "➕ Добавить партнёра")
        def handle_add_partner_button(message):
            self.bot.send_message(message.chat.id, "Введите @username или ID партнёра:")
            self.bot.register_next_step_handler(message, self.lh.process_partner_input)

        @self.bot.message_handler(func=lambda message: message.text == "📝 Добавить список")
        def handle_add_list(message):
            self.bot.send_message(message.chat.id, "Введите название списка:")
            self.bot.register_next_step_handler(message, self.lh.process_list_name)

        @self.bot.message_handler(func=lambda message: message.text == "📋 Мои списки")
        def handle_my_lists(message):
            try:
                user_id = message.from_user.id
                lists = self.db.get_user_lists(user_id)
            except Exception as e:
                self.logger.error(f"[handle_my_lists] Ошибка при получении данных: {e}")

            if not lists:
                self.bot.send_message(user_id, "❗ У вас пока нет списков.")
                return

            try:
                markup = types.InlineKeyboardMarkup()
                for lst in lists:
                    markup.add(types.InlineKeyboardButton(lst['name'], callback_data=f"view_list_{lst['id']}"))

                self.bot.send_message(user_id, "📋 Ваши списки:", reply_markup=markup)
            except Exception as e:
                self.logger.error(f"[handle_my_lists] Ошибка при выводе списков: {e}")