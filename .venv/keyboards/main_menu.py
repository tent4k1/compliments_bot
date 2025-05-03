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

    def get_repeat_menu(selected_option=None): # Создает меню выбора повторения события
        markup = types.InlineKeyboardMarkup(row_width=2)

        daily_btn = types.InlineKeyboardButton(
            "✅ Повторять ежедневно" if selected_option == 'daily' else "🔁 Повторять ежедневно",
            callback_data="repeat_daily"
        )

        once_btn = types.InlineKeyboardButton(
            "✅ Только один раз" if selected_option == 'once' else "📅 Только один раз",
            callback_data="repeat_once"
        )

        markup.add(daily_btn, once_btn)
        return markup

    def get_time_menu(selected_time=None, include_back=True): # Создает меню выбора времени
        markup = types.InlineKeyboardMarkup(row_width=3)

        times = ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00']

        buttons = []
        for t in times:
            prefix = "✅ " if selected_time == t else ""
            buttons.append(
                types.InlineKeyboardButton(f"{prefix}{t}", callback_data=f"time_{t}")
            )

        for i in range(0, len(buttons), 3):
            markup.row(*buttons[i:i + 3])

        all_day_btn = types.InlineKeyboardButton(
            "✅ Весь день" if selected_time == 'allday' else "🌙 Весь день",
            callback_data="time_allday"
        )

        custom_btn = types.InlineKeyboardButton(
            "✏️ Ввести вручную",
            callback_data="time_custom"
        )

        markup.row(all_day_btn)
        markup.row(custom_btn)

        if include_back:
            markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_days"))

        return markup

    @staticmethod
    def get_calendar_menu(include_back=True): # Создает главное меню календаря
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        buttons = [
            types.KeyboardButton("📆 Добавить событие"),
            types.KeyboardButton('📋 Мои события')
        ]

        if include_back:
            buttons.append(types.KeyboardButton('🔙 Назад'))

        markup.add(*buttons)
        return markup

    @staticmethod
    def get_year_menu(current_year=None, years_range=5): # Создает меню выбора года
        markup = types.InlineKeyboardMarkup(row_width=3)
        current_year = current_year or datetime.now().year
        buttons = [
            types.InlineKeyboardButton(
                f"{'✅ ' if year == current_year else ''}{year}",
                callback_data=f'year_{year}'
            )
            for year in range(current_year, current_year + years_range)
        ]
        markup.add(*buttons)
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="main_menu"))
        return markup

    @staticmethod
    def get_month_menu(selected_month=None): # Создает меню выбора месяца с возможностью выделения выбранного
        markup = types.InlineKeyboardMarkup(row_width=4)
        months = [
            ('Январь', 1), ('Февраль', 2), ('Март', 3),
            ('Апрель', 4), ('Май', 5), ('Июнь', 6),
            ('Июль', 7), ('Август', 8), ('Сентябрь', 9),
            ('Октябрь', 10), ('Ноябрь', 11), ('Декабрь', 12)
        ]

        buttons = [
            types.InlineKeyboardButton(
                f"{'✅ ' if num == selected_month else ''}{name}",
                callback_data=f'month_{num}'
            )
            for name, num in months
        ]

        markup.add(*buttons)
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_years"))
        return markup

    @staticmethod
    def get_day_menu(month: int, year: int, selected_day=None): # Создает меню выбора дня с учетом количества дней в месяце
        markup = types.InlineKeyboardMarkup(row_width=7)
        num_days = calendar.monthrange(year, month)[1]

        buttons = [
            types.InlineKeyboardButton(
                f"{'✅ ' if day == selected_day else ''}{day}",
                callback_data=f'day_{day}'
            )
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


