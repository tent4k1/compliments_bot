from telebot.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        KeyboardButton('💝 Получить комплимент'),
        KeyboardButton('📊 Статистика')
    )
    markup.add(
        KeyboardButton('✅ Проверить подписку'),
        KeyboardButton('📋 Вишлист')
    )
    markup.add(
        KeyboardButton('✅ Подписаться'),
        KeyboardButton('❌ Отписаться')
    )
    return markup

def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        KeyboardButton('📝 Добавить комплимент'),
        KeyboardButton('👥 Статистика')
    )
    return markup

