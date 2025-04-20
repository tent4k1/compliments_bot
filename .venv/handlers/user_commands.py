import os
from datetime import datetime
from sched import scheduler

import requests
import logging
import calendar
from telebot import TeleBot, types
from decorators import log_command
from keyboards.main_menu import main_menu
from database import Database
from config import WEATHER, DEFAULT_CITY
from utils.scheduler import ComplimentScheduler

db = Database()
user_event_data = {}
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

    # Обработчик кнопки "Подписка" в главном меню
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
        btn_forecast = types.KeyboardButton('📈 Прогноз погоды')

        markup.add(btn_moscow, btn_podolsk, btn_efremov, btn_dubai, btn_input, btn_back, btn_forecast)
        return markup

    # Обработчик кнопки "Погода" в главном меню
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

    def get_daily_forecast(city_name: str) -> str:
        """Получение и форматирование прогноза погоды"""
        base_url = "http://api.openweathermap.org/data/2.5/forecast"
        params = {
            'q': city_name,
            'appid': WEATHER,
            'units': 'metric',
            'cnt': 8,
            'lang': 'ru'
        }

        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        return format_forecast(response.json())

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
            f"🌡️ Минимальная/Максимальная температура днем: Минимальная - {main['temp_min']}°C Максимальная - {main['temp_max']}°C)\n"
            f"☁️ Состояние: {weather['description'].capitalize()}\n"
            f"💧 Влажность: {main['humidity']}%\n"
            f"🌀 Давление: {main['pressure']} hPa\n"
            f"🌬️ Ветер: {wind['speed']} м/с\n"
            f"🌅 Восход: {sunrise_time}\n"
            f"🌇 Закат: {sunset_time}"
        )

    @bot.message_handler(func=lambda msg: msg.text == '📈 Прогноз погоды')
    @log_command
    def handle_weather_command(message):
        try:
            forecast = get_daily_forecast(DEFAULT_CITY)
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

    def get_weather_icon(weather_id: int) -> str:
        """Возвращает иконку для типа погоды"""
        if 200 <= weather_id < 300:
            return '⛈️'  # Гроза
        elif 300 <= weather_id < 400:
            return '🌧️'  # Морось
        elif 500 <= weather_id < 600:
            return '🌧️'  # Дождь
        elif 600 <= weather_id < 700:
            return '❄️'  # Снег
        elif 700 <= weather_id < 800:
            return '🌫️'  # Атмосферные явления
        elif weather_id == 800:
            return '☀️'  # Ясно
        elif 801 <= weather_id < 900:
            return '☁️'  # Облачно
        else:
            return '🌈'

    @bot.message_handler(func=lambda msg: msg.text == '✔ Установить город по умолчания')
    def set_weather_city(message):
        try:
            city = message.text.split(maxsplit=1)[1]
            # Здесь можно сохранить город для пользователя в БД
            bot.reply_to(message, f"🌆 Город для погоды установлен: {city}")
        except IndexError:
            bot.reply_to(message, "Ошибка")

    def format_forecast(data: dict) -> str:
        """Форматирование данных прогноза"""
        try:
            forecast_lines = []
            for item in data['list']:
                time = datetime.fromtimestamp(item['dt']).strftime('%H:%M')
                temp = item['main']['temp']
                icon = get_weather_icon(item['weather'][0]['id'])
                desc = item['weather'][0]['description'].capitalize()
                forecast_lines.append(f"{icon} {time}: {temp}°C, {desc}")

            return (
                    f"<b>Прогноз в {data['city']['name']}:</b>\n\n" +
                    "\n".join(forecast_lines) +
                    f"\n\n<b>Средняя температура:</b> {sum(i['main']['temp'] for i in data['list']) / 8:.1f}°C"
            )
        except KeyError as e:
            logging.error(f"Missing key in weather data: {str(e)}")
            raise Exception("Некорректные данные о погоде")

    def get_calendar_menu():
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        btn_add_rem = types.KeyboardButton('📆 Добавить событие')
        btn_my_rem = types.KeyboardButton('📋 Мои события')
        btn_del_rem = types.KeyboardButton('❌ Удалить событие')
        btn_back = types.KeyboardButton('🔙 Назад')

        markup.add(btn_my_rem, btn_add_rem, btn_back, btn_del_rem)
        return markup

    @bot.message_handler(func=lambda message: message.text == "🔙 Назад")
    def handle_back(message):
        bot.send_message(message.chat.id, "Вы вернулись в главное меню.", reply_markup=main_menu())

    @bot.message_handler(func=lambda message: message.text == "📅 Календарь")
    def handle_calendar_menu(message):
        bot.send_message(message.chat.id, "🗓 Меню календаря:", reply_markup=get_calendar_menu())

    @bot.message_handler(func=lambda message: message.text == "📆 Добавить событие")
    def handle_add_event(message):
        bot.send_message(message.chat.id, "Выберите год:", reply_markup=get_year_menu())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("year_"))
    def handle_year_selection(call):
        user_id = call.message.chat.id
        selected_year = int(call.data.split("_")[1])

        # Убедитесь, что словарь для пользователя существует
        if user_id not in user_event_data:
            user_event_data[user_id] = {}

        user_event_data[user_id]['year'] = selected_year
        bot.send_message(call.message.chat.id, f"Вы выбрали {selected_year} год. Теперь выберите месяц:",
                         reply_markup=get_month_menu())

    @bot.callback_query_handler(func=lambda call: call.data.startswith('month_'))
    def handle_month_selection(call):
        user_id = call.message.chat.id
        selected_month = int(call.data.split('_')[1])

        user_event_data[user_id]['month'] = selected_month
        bot.send_message(call.message.chat.id, f"Вы выбрали месяц: {selected_month}. Теперь выберите день:",
                         reply_markup=get_day_menu(selected_month, user_event_data[user_id]['year']))

    @bot.callback_query_handler(func=lambda call: call.data.startswith('day_'))
    def handle_day_selection(call):
        user_id = call.message.chat.id
        selected_day = int(call.data.split('_')[1])

        user_event_data[user_id]['day'] = selected_day
        bot.send_message(call.message.chat.id, f"Вы выбрали день: {selected_day}. Теперь выберите время:",
                         reply_markup=get_time_menu())

    @bot.callback_query_handler(func=lambda call: call.data.startswith('time_'))
    def handle_time_selection(call):
        user_id = call.message.chat.id
        selected = call.data.split('_')[1]

        if selected == 'allday':
            user_event_data[user_id]['time'] = '08:00'
            user_event_data[user_id]['all_day'] = 1
        else:
            user_event_data[user_id]['time'] = selected
            user_event_data[user_id]['all_day'] = 0

        bot.send_message(call.message.chat.id,
                         f"Вы выбрали время: {user_event_data[user_id]['time']}. Хотите, чтобы событие повторялось?",
                         reply_markup=get_repeat_menu())

    @bot.message_handler(func=lambda message: message.text == "📋 Мои события")
    def handle_view_events(message):
        user_id = message.from_user.id
        events = db.get_all_events(user_id=user_id)

        if not events:
            bot.send_message(message.chat.id, "У вас нет сохранённых событий.")
            return

        for event in events:
            id = event[0]
            year = event[1]
            month = event[2]
            day = event[3]
            time = event[4]
            description = event[5]
            repeat = event[6] if len(event) > 6 else 0

            # Формирование даты
            if year and month and day:
                date_str = f"{int(year)}-{int(month):02d}-{int(day):02d}"
            else:
                date_str = "⏰ Повторяется ежедневно" if repeat else "❓ Дата не указана"

            text = f"📅 ID: {id} | {date_str} в {time}\n📝 {description}"

            # Кнопка удаления
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{id}"))

            bot.send_message(message.chat.id, text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data in ["repeat_daily", "repeat_once"])
    def handle_repeat_selection(call):
        user_id = call.message.chat.id
        user_event_data[user_id]['repeat'] = 1 if call.data == "repeat_daily" else 0
        bot.send_message(call.message.chat.id, "✏️ Введите описание события:")

    @bot.message_handler(
        func=lambda message: message.text and user_event_data.get(message.chat.id, {}).get('repeat') is not None)
    def handle_event_description(message):
        user_id = message.chat.id
        event_description = message.text.strip()

        if user_id not in user_event_data:
            user_event_data[user_id] = {}

        # Убедитесь, что все необходимые данные для события есть
        if 'year' not in user_event_data[user_id]:
            bot.send_message(message.chat.id, "⛔ Пожалуйста, сначала выберите год для события.")
            return
        if 'month' not in user_event_data[user_id]:
            bot.send_message(message.chat.id, "⛔ Пожалуйста, сначала выберите месяц для события.")
            return
        if 'day' not in user_event_data[user_id]:
            bot.send_message(message.chat.id, "⛔ Пожалуйста, сначала выберите день для события.")
            return
        if 'time' not in user_event_data[user_id]:
            bot.send_message(message.chat.id, "⛔ Пожалуйста, сначала выберите время для события.")
            return

        # Сохраняем описание события
        user_event_data[user_id]['event_description'] = event_description

        try:
            # Сохраняем данные события в базе данных
            db.save_event(
                user_id=user_id,
                year=user_event_data[user_id]['year'],
                month=user_event_data[user_id]['month'],
                day=user_event_data[user_id]['day'],
                time=user_event_data[user_id]['time'],
                event_description=user_event_data[user_id]['event_description'],
                all_day=user_event_data[user_id].get('all_day', 0),
                repeat=user_event_data[user_id].get('repeat', 0)
            )
            bot.send_message(message.chat.id, "✅ Событие сохранено!")

            # Планируем напоминание
            scheduler = ComplimentScheduler(bot, db)
            scheduler.schedule_event_reminder(user_event_data[user_id], user_id)

            # Очищаем данные пользователя после сохранения
            del user_event_data[user_id]

        except Exception as e:
            print(f"Ошибка при сохранении события: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка при сохранении события.")

    def get_year_menu(start_year=None, years_forward=3):
        if start_year is None:
            start_year = datetime.now().year

        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = [
            types.InlineKeyboardButton(str(year), callback_data=f"year_{year}")
            for year in range(start_year, start_year + years_forward)
        ]
        markup.add(*buttons)
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="main_menu"))
        return markup

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_years")
    def back_to_years(call):
        bot.send_message(call.message.chat.id, "Выберите год:", reply_markup=get_year_menu())

    def get_month_menu():
        markup = types.InlineKeyboardMarkup(row_width=2)
        months = [
            ('Январь', '01'), ('Февраль', '02'), ('Март', '03'),
            ('Апрель', '04'), ('Май', '05'), ('Июнь', '06'),
            ('Июль', '07'), ('Август', '08'), ('Сентябрь', '09'),
            ('Октябрь', '10'), ('Ноябрь', '11'), ('Декабрь', '12')
        ]
        buttons = [types.InlineKeyboardButton(name, callback_data=f'month_{num}') for name, num in months]
        markup.add(*buttons)
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_years"))
        return markup

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_months")
    def back_to_months(call):
        bot.send_message(call.message.chat.id, "Выберите месяц:", reply_markup=get_month_menu())

    def get_day_menu(month: int, year: int):
        markup = types.InlineKeyboardMarkup(row_width=2)
        num_days = calendar.monthrange(year, month)[1]
        buttons = [
            types.InlineKeyboardButton(str(day), callback_data=f'day_{day}')
            for day in range(1, num_days + 1)
        ]
        markup.add(*buttons)
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_months"))
        return markup

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_days")
    def back_to_days(call):
        bot.send_message(call.message.chat.id, "Выберите день:", reply_markup=get_day_menu())

    def get_time_menu():
        markup = types.InlineKeyboardMarkup()
        times = ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00']
        for t in times:
            markup.add(types.InlineKeyboardButton(t, callback_data=f"time_{t}"))
        markup.add(types.InlineKeyboardButton("🌙 На весь день", callback_data="time_allday"))
        markup.add(types.InlineKeyboardButton("🕓 Ввести вручную", callback_data="time_custom"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_days"))
        return markup

    @bot.callback_query_handler(func=lambda call: call.data == 'time_custom')
    def handle_custom_time(call):
        user_id = call.message.chat.id
        user_event_data[user_id] = {}

        user_event_data[user_id]['awaiting_time'] = True
        bot.send_message(call.message.chat.id, "Пожалуйста, введите время в формате ЧЧ:ММ (например, 14:30).")
        bot.register_next_step_handler(call.message, process_custom_time)

    @bot.message_handler(
        func=lambda message: message.text and user_event_data.get(message.chat.id, {}).get("awaiting_time"))
    def process_custom_time(message):
        user_id = message.chat.id
        time_input = message.text.strip()

        try:
            # Пробуем преобразовать строку в время
            datetime.datetime.strptime(time_input, "%H:%M")

            # Сохраняем время и сбрасываем флаг
            user_event_data[user_id]['time'] = time_input
            user_event_data[user_id]['awaiting_time'] = False
            user_event_data[user_id]['all_day'] = 0  # Если время указано вручную, не весь день

            # Запрашиваем описание события
            bot.send_message(message.chat.id,
                             f"Вы установили время: {time_input}. Хотите, чтобы событие повторялось?",
                             reply_markup=get_repeat_menu())
        except ValueError:
            bot.send_message(message.chat.id, "⛔ Неверный формат времени. Пожалуйста, введите в формате ЧЧ:ММ.")

    def get_repeat_menu():
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🔁 Повторять ежедневно", callback_data="repeat_daily"),
            types.InlineKeyboardButton("📅 Только один раз", callback_data="repeat_once"),
        )
        return markup

    def handle_time_input(message):
        user_time = message.text.strip()

        # Проверка на правильность формата
        if len(user_time) == 5 and user_time[2] == ":" and user_time[:2].isdigit() and user_time[3:].isdigit():
            event_data['time'] = user_time
            bot.send_message(message.chat.id, f"Вы выбрали время: {user_time}. Введите описание события.")
            bot.register_next_step_handler(message, handle_event_description)
        else:
            bot.send_message(message.chat.id, "Неверный формат времени. Пожалуйста, введите снова в формате ЧЧ:ММ.")
            bot.register_next_step_handler(message, handle_time_input)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
    def handle_delete_event(call):
        id = int(call.data.split("_")[1])
        try:
            if db.delete_event(id):  # Пытаемся удалить событие
                bot.answer_callback_query(call.id, text="Событие удалено ✅")
                bot.send_message(call.message.chat.id, f"✅ Событие с ID {id} удалено.")
            else:
                bot.answer_callback_query(call.id, text="Событие не найдено ❌")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❗️ Ошибка при удалении: {e}")

    @bot.message_handler(commands=['delete_event'])
    def process_event_deletion(message):
        events = db.get_all_events(user_id=message.from_user.id)
        if not events:
            bot.send_message(message.chat.id, "У вас нет сохранённых событий.")
            return

        for event in events:
            id, year, month, day, time, event_description = event
            text = f"📅 ID: {id} | {year}-{int(month):02d}-{int(day):02d} в {time}\n📝 {event_description}"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{id}"))
            bot.send_message(message.chat.id, text, reply_markup=markup)

    @bot.message_handler(func=lambda message: message.text == "❌ Удалить событие")
    def handle_delete_event_menu(message):
        user_id = message.from_user.id
        events = db.get_all_events(user_id=user_id)  # Получаем все события пользователя

        if events:
            for event in events:
                id, year, month, day, time, event_description = event
                event_text = f"📅 ID: {id} | {year}-{int(month):02d}-{int(day):02d} в {time} — {event_description}"

                # Создаем кнопку для удаления
                markup = types.InlineKeyboardMarkup()
                delete_button = types.InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{id}")
                markup.add(delete_button)

                # Отправляем сообщение с кнопкой удаления
                bot.send_message(message.chat.id, event_text, reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "У вас нет сохранённых событий.")