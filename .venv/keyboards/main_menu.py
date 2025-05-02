import calendar
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from telebot import TeleBot, types
from datetime import datetime

class Buttons_menu:
    @staticmethod
    def main_menu():
        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(
            KeyboardButton('💝 Получить комплимент'),
            KeyboardButton('📊 Статистика')
        )
        markup.add(
            KeyboardButton('☑ Подписка'),
            KeyboardButton('📋 Вишлист')
        )
        markup.add(
            KeyboardButton('🌡 Погода'),
            KeyboardButton("📅 Календарь"),
        )

        return markup

    @staticmethod
    def admin_menu():
        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(
            KeyboardButton('📝 Добавить комплимент'),
            KeyboardButton('👥 Статистика')
        )
        return markup

    @staticmethod
    def get_repeat_menu():
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🔁 Повторять ежедневно", callback_data="repeat_daily"),
            types.InlineKeyboardButton("📅 Только один раз", callback_data="repeat_once"),
        )
        return markup

    @staticmethod
    def get_time_menu():
        markup = types.InlineKeyboardMarkup()
        times = ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00']
        for t in times:
            markup.add(types.InlineKeyboardButton(t, callback_data=f"time_{t}"))
        markup.row(types.InlineKeyboardButton("🌙 На весь день", callback_data="time_allday"))
        markup.row(types.InlineKeyboardButton("🕓 Ввести вручную", callback_data="time_custom"))
        markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_days"))
        return markup

    @staticmethod
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

    @staticmethod
    def get_calendar_menu():
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        btn_add_rem = types.KeyboardButton('📆 Добавить событие')
        btn_my_rem = types.KeyboardButton('📋 Мои события')
        btn_del_rem = types.KeyboardButton('❌ Удалить событие')
        btn_back = types.KeyboardButton('🔙 Назад')

        markup.add(btn_my_rem, btn_add_rem, btn_back, btn_del_rem)
        return markup

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def get_subscribe_keyboard():
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        btn_check = types.KeyboardButton('❓ Проверить подписку')
        btn_subs = types.KeyboardButton('✅ Подписаться')
        btn_unsubs = types.KeyboardButton('❌ Отписаться')
        btn_back = types.KeyboardButton('🔙 Назад')
        markup.add(btn_check, btn_subs, btn_unsubs, btn_back)
        return markup

    @staticmethod
    def get_reminder_offset_menu():
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("За 15 минут", callback_data="reminder_15"),
            types.InlineKeyboardButton("За 1 час", callback_data="reminder_60"),
            types.InlineKeyboardButton("За 2 часа", callback_data="reminder_120"),
            types.InlineKeyboardButton("За 3 часа", callback_data="reminder_180"),
            types.InlineKeyboardButton("За 12 часов", callback_data="reminder_720"),
            types.InlineKeyboardButton("За 1 день", callback_data="reminder_1440"),
            types.InlineKeyboardButton("Не напоминать", callback_data="reminder_none")
        )
        return markup
