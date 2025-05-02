import logging
from datetime import datetime
from itertools import groupby

from database import Database
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from telebot import TeleBot, types
from config import TOKEN

logger = logging.getLogger("telebot")
logger.setLevel(logging.DEBUG)
bot = TeleBot(TOKEN)
db = Database()

class Reminders_Handlers:
    @staticmethod
    def group_events_by_date(events):
        sorted_events = sorted(events, key=lambda x: (x['year'], x['month'], x['day']))
        return groupby(sorted_events, key=lambda x: f"{x['day']}.{x['month']}.{x['year']}")

    @staticmethod
    def get_status_icon(event):
        event_date = datetime(event['year'], event['month'], event['day'])
        delta = (event_date - datetime.now()).days

        if delta < 0:
            return "🔴"  # Просрочено
        elif delta == 0:
            return "🟠"  # Сегодня
        elif delta <= 3:
            return "🟡"  # Скоро
        else:
            return "🟢"  # Есть время

    @staticmethod
    def send_grouped_events(chat_id, events, page=0, message_id=None):
        if not isinstance(events, list):
            logger.error(f"Expected list, got {type(events)}: {events}")
            bot.send_message(chat_id, "❌ Ошибка: неверный формат событий")
            return

        if not events:
            if message_id:
                bot.edit_message_text("У вас нет событий", chat_id, message_id)
            else:
                bot.send_message(chat_id, "У вас нет событий")
            return

        try:
            events_sorted = sorted(
                [e for e in events if isinstance(e, dict)],
                key=lambda x: (
                    int(x.get('year', 0)),
                    int(x.get('month', 0)),
                    int(x.get('day', 0))
                )
            )
        except Exception as e:
            logger.warning(f"Ошибка при сортировке событий: {e}")

        grouped_events = {}

        for event in events_sorted:
            month = f"{int(event['month']):02d}"
            date_key = f"{event['day']}.{month}.{event['year']}"

            if date_key not in grouped_events:
                grouped_events[date_key] = []
            grouped_events[date_key].append(event)

        dates = list(grouped_events.keys())
        pages = [dates[i:i + 3] for i in range(0, len(dates), 3)]

        if page >= len(pages):
            page = len(pages) - 1

        current_page = pages[page]
        text = f"📅 Ваши события (страница {page + 1}/{len(pages)})\n\n"

        for date in current_page:
            text += f"🗓 *{date}*\n"
            for event in grouped_events[date]:
                time = event['time'] if event.get('time') else "⏰ Весь день"
                text += f"    - {time}: {event['event_description']} "
                text += f"[ID: {event['id']}]\n"
            text += "\n"

        markup = types.InlineKeyboardMarkup()

        if len(pages) > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"page_{page - 1}"))
            nav_buttons.append(types.InlineKeyboardButton(f"{page + 1}/{len(pages)}", callback_data="current"))
            if page < len(pages) - 1:
                nav_buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"page_{page + 1}"))
            markup.row(*nav_buttons)

        markup.row(
            types.InlineKeyboardButton("✏️ Редактировать", callback_data="edit_mode"),
            types.InlineKeyboardButton("❌ Удалить", callback_data="delete_mode")
        )

        if message_id:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

    def process_new_text(self, message, event_id, original_call):
        try:
            new_text = message.text.strip()
            if not new_text:
                bot.send_message(message.chat.id, "Текст не может быть пустым")
                return

            if db.update_event_description(event_id, new_text):
                bot.send_message(message.chat.id, "Описание обновлено ✅")

                # Обновляем список событий
                events = db.get_all_events(message.from_user.id)
                self.send_grouped_events(
                    chat_id=message.chat.id,
                    events=events,
                    message_id=original_call.message.message_id
                )
            else:
                bot.send_message(message.chat.id, "❌ Ошибка обновления")

        except Exception as e:
            logger.error(f"Error in process_new_text: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка")

