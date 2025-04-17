import os
from datetime import datetime
import requests
from telebot import TeleBot, types
from decorators import log_command
from keyboards.main_menu import main_menu
from database import Database
from config import WEATHER

db = Database()


def setup_user_commands(bot: TeleBot, scheduler):
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
    def get_subscribe_keyboard():
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        btn_check = types.KeyboardButton('❓ Проверить подписку')
        btn_subs = types.KeyboardButton('✅ Подписаться')
        btn_unsubs = types.KeyboardButton('❌ Отписаться')
        btn_back = types.KeyboardButton('🔙 Назад')
        markup.add(btn_check, btn_subs, btn_unsubs, btn_back)
        return markup

    # Обработчик кнопки "Вишлист" в главном меню
    @bot.message_handler(func=lambda msg: msg.text == '☑ Подписка')
    @log_command
    def subscribe_menu(message):
        bot.send_message(
            message.chat.id,
            "☑ Управление подпиской:",
            reply_markup=get_subscribe_keyboard()
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
    def get_weather_keyboard():
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        btn_moscow = types.KeyboardButton('Москва')
        btn_podolsk = types.KeyboardButton('Подольск')
        btn_efremov = types.KeyboardButton('Ефремов')
        btn_dubai = types.KeyboardButton('Дубай')
        btn_input = types.KeyboardButton('🌍 Ввести другой город')
        btn_back = types.KeyboardButton('🔙 Назад')
        markup.add(btn_moscow, btn_podolsk, btn_efremov, btn_dubai, btn_input, btn_back)
        return markup

    # Обработчик кнопки "Вишлист" в главном меню
    @bot.message_handler(func=lambda msg: msg.text == '🌡 Погода')
    @log_command
    def weather_menu(message):
        bot.send_message(
            message.chat.id,
            "⌨ Выбор города:",
            reply_markup=get_weather_keyboard()
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
            weather_data = get_weather_data(city)
            response = format_weather_response(weather_data)
            bot.send_message(
                message.chat.id,
                response,
                reply_markup=get_weather_keyboard(),
                parse_mode='HTML'
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return "Город не найден"
            elif e.response.status_code == 401:
                return "Ошибка API ключа"
            else:
                return "Ошибка сервера"

    def get_weather_data(city_name: str) -> dict:
        base_url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            'q': city_name,
            'appid': WEATHER,
            'units': 'metric',
            'lang': 'ru'
        }
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        return response.json()

    def format_weather_response(data: dict) -> str:
        weather = data['weather'][0]
        main = data['main']
        wind = data['wind']
        sys = data['sys']
        sunrise = datetime.fromtimestamp(sys['sunrise'])
        sunset = datetime.fromtimestamp(sys['sunset'])
        sunrise_time = sunrise.strftime('%H:%M')
        sunset_time = sunset.strftime('%H:%M')
        sunrise.strftime('%H:%M')

        return (
            f"<b>Погода в {data['name']}:</b>\n\n"
            f"🌡️ Температура: {main['temp']}°C (ощущается как {main['feels_like']}°C)\n"
            f"☁️ Состояние: {weather['description'].capitalize()}\n"
            f"💧 Влажность: {main['humidity']}%\n"
            f"🌀 Давление: {main['pressure']} hPa\n"
            f"🌬️ Ветер: {wind['speed']} м/с\n"
            f"🌅 Восход: {sunrise_time}\n"
            f"🌇 Закат: {sunset_time}"
        )
