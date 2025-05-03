import logging
from datetime import datetime
from itertools import groupby
from sched import scheduler

from database import Database
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from telebot import TeleBot, types
from config import TOKEN

class DeleteState:
    def __init__(self):
        self.selected_events = {}

class Reminders_Handlers:
    def __init__(self, bot, db, bm, scheduler):
        self.bot = bot
        self.db = db
        self.bm = bm
        self.scheduler = scheduler
        self.logger = logging.getLogger(__name__)
        self.delete_state = DeleteState()
        self._register_handlers()
        self.user_event_data = {}

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

    def send_grouped_events(self, chat_id, events, page=0, message_id=None):
        if not isinstance(events, list):
            self.logger.error(f"Expected list, got {type(events)}: {events}")
            self.bot.send_message(chat_id, "❌ Ошибка: неверный формат событий")
            return

        if not events:
            if message_id:
                self.bot.edit_message_text("У вас нет событий", chat_id, message_id)
            else:
                self.bot.send_message(chat_id, "У вас нет событий")
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
            self.logger.warning(f"Ошибка при сортировке событий: {e}")

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
            self.bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        else:
            self.bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

    def process_new_text(self, message, event_id, original_call):
        try:
            new_text = message.text.strip()
            if not new_text:
                self.bot.send_message(message.chat.id, "Текст не может быть пустым")
                return

            if self.db.update_event_description(event_id, new_text):
                self.bot.send_message(message.chat.id, "Описание обновлено ✅")

                events = self.db.get_all_events(message.from_user.id)
                self.send_grouped_events(
                    chat_id=message.chat.id,
                    events=events,
                    message_id=original_call.message.message_id
                )
            else:
                self.bot.send_message(message.chat.id, "❌ Ошибка обновления")

        except Exception as e:
            self.logger.error(f"Error in process_new_text: {e}")
            self.bot.send_message(message.chat.id, "❌ Произошла ошибка")

    def start_event_creation(self, user_id):
        if user_id not in self.user_event_data:
            self.user_event_data[user_id] = {}
        return self.bm.get_year_menu()

    def _register_handlers(self):
        @self.bot.callback_query_handler(func=lambda call: call.data == ("add_reminder"))
        def handle_add_event(message):
            user_id = message.chat.id
            if user_id not in self.user_event_data:
                self.user_event_data[user_id] = {}
            self.bot.send_message(user_id, "Выберите год:", reply_markup=self.bm.get_year_menu())

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("year_"))
        def handle_year_selection(call):
            user_id = call.message.chat.id
            try:
                selected_year = int(call.data.split("_")[1])
                self.user_event_data[user_id]['year'] = selected_year
                self.bot.edit_message_text(
                    f"Вы выбрали {selected_year} год. Теперь выберите месяц:",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=self.bm.get_month_menu()
                )
            except Exception as e:
                self.logger.error(f"Error in year selection: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка выбора года")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('month_'))
        def handle_month_selection(call):
            user_id = call.message.chat.id
            try:
                selected_month = int(call.data.split('_')[1])
                self.user_event_data[user_id]['month'] = selected_month
                year = self.user_event_data[user_id].get('year', datetime.now().year)
                self.bot.edit_message_text(
                    f"Вы выбрали месяц: {selected_month}. Теперь выберите день:",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=self.bm.get_day_menu(selected_month, year)
                )
            except Exception as e:
                self.logger.error(f"Error in month selection: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка выбора месяца")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('day_'))
        def handle_day_selection(call):
            user_id = call.message.chat.id
            try:
                selected_day = int(call.data.split('_')[1])
                self.user_event_data[user_id]['day'] = selected_day
                self.bot.edit_message_text(
                    f"Вы выбрали день: {selected_day}. Теперь выберите время:",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=self.bm.get_time_menu()
                )
            except Exception as e:
                self.logger.error(f"Error in day selection: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка выбора дня")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('time_'))
        def handle_time_selection(call):
            user_id = call.message.chat.id
            try:
                selected = call.data.split('_')[1]

                if selected == 'allday':
                    self.user_event_data[user_id]['time'] = '08:00'
                    self.user_event_data[user_id]['all_day'] = 1
                    self.bot.edit_message_text(
                        "Вы выбрали: весь день. Хотите, чтобы событие повторялось?",
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=self.bm.get_reminder_offset_menu()
                    )
                elif selected == 'custom':
                    self.user_event_data[user_id]['awaiting_time'] = True
                    self.bot.send_message(user_id, "Введите время в формате ЧЧ:ММ (например, 09:30):")
                else:
                    self.user_event_data[user_id]['time'] = selected
                    self.user_event_data[user_id]['all_day'] = 0
                    self.bot.edit_message_text(
                        f"Вы выбрали время: {selected}. Теперь выберите, за сколько времени напомнить:",
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=self.bm.get_reminder_offset_menu()
                    )
            except Exception as e:
                self.logger.error(f"Error in time selection: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка выбора времени")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('reminder_'))
        def handle_reminder_offset_selection(call):
            user_id = call.message.chat.id
            try:
                offset = call.data.split('_')[1]
                if offset == 'none':
                    self.user_event_data[user_id]['reminder_offset'] = 0
                else:
                    self.user_event_data[user_id]['reminder_offset'] = int(offset)

                self.bot.edit_message_text(
                    "Хотите, чтобы событие повторялось ежедневно или было одноразовым?",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=self.bm.get_repeat_menu()
                )
            except Exception as e:
                self.logger.error(f"Error in reminder offset selection: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка выбора напоминания")

        @self.bot.callback_query_handler(func=lambda call: call.data in ["repeat_daily", "repeat_once"])
        def handle_repeat_selection(call):
            user_id = call.message.chat.id
            try:
                self.user_event_data[user_id]['repeat'] = 1 if call.data == "repeat_daily" else 0
                self.bot.edit_message_text(
                    "✏️ Введите описание события:",
                    call.message.chat.id,
                    call.message.message_id
                )
            except Exception as e:
                self.logger.error(f"Error in repeat selection: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка выбора повторения")

        @self.bot.message_handler(func=lambda message: self.user_event_data.get(message.chat.id, {}).get('repeat') is not None)
        def handle_event_description(message):
            user_id = message.chat.id
            event_data = self.user_event_data.get(user_id, {})

            required_fields = ['year', 'month', 'day', 'time']
            if not all(field in event_data for field in required_fields):
                missing = [f for f in required_fields if f not in event_data]
                self.bot.send_message(user_id, f"⛔ Не хватает данных: {', '.join(missing)}")
                return

            event_description = message.text.strip()
            try:
                event_id = self.db.save_event(
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
                    self.bot.send_message(user_id, "❌ Ошибка сохранения события в БД")
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

                if self.scheduler.schedule_event_reminder(event_data_for_scheduler, user_id):
                    self.bot.send_message(user_id, "✅ Событие сохранено и напоминание установлено!")
                else:
                    self.bot.send_message(user_id, "⚠️ Событие сохранено, но не удалось установить напоминание")

                self.user_event_data.pop(user_id, None)

            except Exception as e:
                self.logger.error(f"System error in handle_event_description: {e}")
                self.bot.send_message(user_id, "❌ Произошла системная ошибка при обработке события")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("del_confirm"))
        def confirm_deletion(call):
            try:
                user_id = call.from_user.id

                if user_id not in self.delete_state.selected_events or not self.delete_state.selected_events[user_id]:
                    self.bot.answer_callback_query(call.id, "Не выбрано ни одного события", show_alert=True)
                    return

                deleted_count = 0
                for event_id in list(self.delete_state.selected_events[user_id]):
                    if self.db.delete_event(event_id, user_id=user_id):
                        deleted_count += 1

                del self.delete_state.selected_events[user_id]

                events = self.db.get_all_events(user_id)
                self.send_grouped_events(
                    chat_id=call.message.chat.id,
                    events=events,
                    message_id=call.message.message_id
                )

                self.bot.answer_callback_query(call.id, f"Удалено событий: {deleted_count}", show_alert=True)

            except Exception as e:
                self.logger.error(f"Error in confirm_deletion: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка при удалении")

        @self.bot.callback_query_handler(func=lambda call: call.data == "del_cancel")
        def cancel_deletion(call):
            try:
                user_id = call.from_user.id

                if user_id in self.delete_state.selected_events:
                    del self.delete_state.selected_events[user_id]

                events = self.db.get_all_events(user_id)
                self.send_grouped_events(
                    chat_id=call.message.chat.id,
                    events=events,
                    message_id=call.message.message_id
                )

                self.bot.answer_callback_query(call.id, "Удаление отменено")

            except Exception as e:
                self.logger.error(f"Error in cancel_deletion: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка при отмене")

        @self.bot.callback_query_handler(func=lambda call: call.data == "delete_mode")
        def handle_delete_mode(call):
            try:
                user_id = call.from_user.id
                events = self.db.get_all_events(user_id=user_id)

                if not events:
                    self.bot.answer_callback_query(call.id, "Нет событий для удаления", show_alert=True)
                    return

                self.delete_state.selected_events[user_id] = set()

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

                self.bot.edit_message_text(
                    "🗑 Выберите события для удаления:",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )

            except Exception as e:
                self.logger.error(f"Error in enter_delete_mode: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка при входе в режим удаления")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("del_toggle_"))
        def toggle_event_selection(call):
            try:
                user_id = call.from_user.id
                event_id = int(call.data.split("_")[2])

                if user_id not in self.delete_state.selected_events:
                    self.delete_state.selected_events[user_id] = set()

                if event_id in self.delete_state.selected_events[user_id]:
                    self.delete_state.selected_events[user_id].remove(event_id)
                    new_prefix = "🔘"
                else:
                    self.delete_state.selected_events[user_id].add(event_id)
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
                            elif btn_event_id in self.delete_state.selected_events[user_id]:
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
                    self.bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=new_text,
                        reply_markup=markup
                    )

                self.bot.answer_callback_query(call.id)

            except Exception as e:
                self.logger.error(f"Error in toggle_event_selection: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка выбора события")

        @self.bot.message_handler(func=lambda message: self.user_event_data.get(message.chat.id, {}).get('awaiting_time'))
        def process_custom_time(message):
            user_id = message.chat.id
            time_input = message.text.strip()

            try:
                datetime.strptime(time_input, "%H:%M")
                self.user_event_data[user_id]['time'] = time_input
                self.user_event_data[user_id]['awaiting_time'] = False

                self.bot.send_message(
                    user_id,
                    f"Вы установили время: {time_input}. Теперь выберите, за сколько времени напомнить:",
                    reply_markup=self.bm.get_reminder_offset_menu()
                )
            except ValueError:
                self.bot.send_message(user_id, "⛔ Неверный формат времени. Пожалуйста, введите в формате ЧЧ:ММ.")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith(("events_prev_", "events_next_")))
        def handle_events_pagination(call):
            try:
                _, direction, page = call.data.split('_')
                page = int(page)
                new_page = page - 1 if direction == "prev" else page + 1

                events = self.db.get_all_events(call.from_user.id)

                self.send_grouped_events(
                    chat_id=call.message.chat.id,
                    events=events,
                    page=new_page,
                    message_id=call.message.message_id
                )

            except Exception as e:
                self.logger.error(f"Error in handle_events_pagination: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка при переключении страницы")

        @self.bot.callback_query_handler(func=lambda call: call.data == "edit_mode")
        def enter_edit_mode(call):
            events = self.db.get_all_events(call.from_user.id)
            markup = types.InlineKeyboardMarkup()

            for event in events:
                btn_text = f"{event['day']}.{event['month']} {event.get('time', '')} - {event['event_description'][:15]}..."
                markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"edit_{event['id']}"))

            markup.row(
                types.InlineKeyboardButton("◀️ Назад", callback_data="cancel_edit")
            )

            self.bot.edit_message_text(
                "Выберите событие для редактирования:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("edit_"))
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

            self.bot.edit_message_text(
                "Что хотите изменить?",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("edittext_"))
        def edit_event_text(call):
            try:
                event_id = call.data.split("_")[1]
                msg = self.bot.send_message(call.message.chat.id, "Введите новое описание события:")

                self.bot.register_next_step_handler(msg, self.process_new_text, event_id=event_id, original_call=call)

            except Exception as e:
                self.logger.error(f"Error in edit_event_text: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка при редактировании")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("page_"))
        def handle_pagination(call):
            page = int(call.data.split("_")[1])
            events = self.db.get_all_events(call.from_user.id)
            self.send_grouped_events(
                call.message.chat.id,
                events,
                page=page,
                message_id=call.message.message_id
            )

        @self.bot.callback_query_handler(func=lambda call: call.data == "cancel_edit")
        def handle_cancel_edit(call):
            try:
                user_id = call.from_user.id
                events = self.db.get_all_events(user_id=user_id)

                self.send_grouped_events(
                    chat_id=call.message.chat.id,
                    events=events,
                    message_id=call.message.message_id
                )

                self.bot.answer_callback_query(call.id, "Редактирование отменено")

            except Exception as e:
                self.logger.error(f"Error in handle_cancel_edit: {e}")
                self.bot.answer_callback_query(call.id, "❌ Ошибка при отмене")

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

            self.bot.send_message(chat_id, text, reply_markup=markup)

        @self.bot.callback_query_handler(func=lambda call: call.data == "main_menu")
        def handle_back_to_menu(call):
            try:
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Вы вернулись в меню календаря",
                    reply_markup=self.bm.get_calendar_menu()
                )
            except Exception as e:
                self.logger.error(f"Error in handle_back_to_menu: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка при возврате в меню")

        @self.bot.callback_query_handler(func=lambda call: call.data == "back_to_years")
        def handle_back_to_years(call):
            try:
                self.bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=self.bm.get_year_menu()
                )
                self.bot.answer_callback_query(call.id)
            except Exception as e:
                self.logger.error(f"Error in handle_back_to_years: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка при возврате к выбору года")

        @self.bot.callback_query_handler(func=lambda call: call.data == "back_to_months")
        def handle_back_to_months(call):
            try:
                user_id = call.from_user.id
                year = self.user_event_data[user_id].get('year', datetime.now().year)

                self.bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=self.bm.get_month_menu()
                )
                self.bot.answer_callback_query(call.id)
            except Exception as e:
                self.logger.error(f"Error in handle_back_to_months: {e}")
                self.bot.answer_callback_query(call.id, "Ошибка при возврате к выбору месяца")

