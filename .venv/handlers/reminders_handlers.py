import logging
import re
from datetime import datetime
from itertools import groupby

from parsers.reminder_parser import ReminderParser
from database import Database
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from telebot import TeleBot, types

class DeleteState:
    def __init__(self):
        self.selected_events = {}

class Reminders_Handlers:
    def __init__(self, bot, db, bm, scheduler):
        self.bot = bot
        self.db = db
        self.bm = bm
        self.scheduler = scheduler
        self.parser = ReminderParser()
        self.logger = logging.getLogger(__name__)
        self.delete_state = DeleteState()
        self._register_handlers()
        self.user_event_data = {}

    def _handle_callback_error(self, call, message, exception): # Обработка ошибок
        self.logger.error(f"{message}: {exception}")
        self.bot.answer_callback_query(call.id, message)

    @staticmethod
    def group_events_by_date(events): # Сортировка событий по дате
        try:
            sorted_events = sorted(
                events,
                key=lambda x: (
                    int(x.get('year') or 0),
                    int(x.get('month') or 0),
                    int(x.get('day') or 0)
                )
            )
            return groupby(sorted_events, key=lambda x: f"{x['day']}.{x['month']}.{x['year']}")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Ошибка при сортировке событий: {e}")

    @staticmethod
    def get_status_icon(event): # Выбор иконки для события (при выводе пользователю)
        try:
            event_date = datetime(
                int(event['year']),
                int(event['month']),
                int(event['day'])
            )
            delta = (event_date - datetime.now()).days

            if delta < 0:
                return "🔴"
            elif delta == 0:
                return "🟠"
            elif delta <= 3:
                return "🟡"
            else:
                return "🟢"
        except Exception as e:
            logging.getLogger(__name__).warning(f"Ошибка в get_status_icon: {e}")
            return "❓"

    @staticmethod
    def escape_markdown_v2(text: str) -> str: # Экранирование символов
        try:
            escape_chars = r'\_*[]()~`>#+-=|{}.!'
            return re.sub(rf'([{re.escape(escape_chars)}])', r'\\\1', text)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Ошибка при экранировании символов: {e}")

    def send_grouped_events(self,
                            chat_id: int, events: list,
                            page: int = 0, message_id: int = None) -> None: # Отправка группированного списка событий
        if not isinstance(events, list):
            self.logger.error(f"Invalid events type: {type(events)}")
            self._send_error_message(chat_id, message_id, "❌ Ошибка: неверный формат событий")
            return

        if not events:
            self._send_empty_events_message(chat_id, message_id)
            return

        try:
            grouped_events = self._prepare_grouped_events(events)
            if not grouped_events:
                self._send_empty_events_message(chat_id, message_id)
                return

            pages = self._split_into_pages(grouped_events)
            page = self._validate_page_number(page, pages)

            text = self._generate_events_text(grouped_events, pages, page)

            markup = self.bm.create_events_markup(pages, page)

            self._send_or_edit_message(chat_id, text, markup, message_id)

        except Exception as e:
            self.logger.error(f"Error in send_grouped_events: {str(e)}", exc_info=True)
            self._send_error_message(chat_id, message_id, "❌ Произошла ошибка при обработке событий")

    def _prepare_grouped_events(self, events: list) -> dict: # Группирует события по датам и возвращает словарь
        grouped = self.group_events_by_date(events)
        return {key: list(group) for key, group in grouped}

    def _split_into_pages(self, grouped_events: dict, items_per_page: int = 3) -> list: # Разбивает даты на страницы
        dates = list(grouped_events.keys())
        return [dates[i:i + items_per_page] for i in range(0, len(dates), items_per_page)]

    def _validate_page_number(self, page: int, pages: list) -> int: # Корректирует номер страницы при выходе за границы
        return min(max(0, page), len(pages) - 1)

    def _generate_events_text(self, grouped_events: dict,
                              pages: list, current_page: int) -> str: # Генерирует текст сообщения с событиями
        text = [f"*📅 Ваши события \\(страница {current_page + 1}/{len(pages)}\\)*\n"]

        for date in pages[current_page]:
            text.append(f"*🗓 {self.escape_markdown_v2(date)}*")
            for event in grouped_events[date]:
                time = event.get('time', "⏰ Весь день")
                icon = self.get_status_icon(event)
                desc = self.escape_markdown_v2(event['event_description'])
                eid = self.escape_markdown_v2(str(event.get('id', '')))
                text.append(f"    \\- {icon} {self.escape_markdown_v2(time)}: {desc} \\[ID: {eid}\\]")
            text.append("")

        return "\n".join(text)

    def _send_or_edit_message(self, chat_id: int, text: str, markup: types.InlineKeyboardMarkup,
                              message_id: int = None) -> None: # Отправляет новое сообщение или редактирует существующее
        if message_id:
            self.bot.edit_message_text(
                text, chat_id, message_id,
                reply_markup=markup,
                parse_mode="MarkdownV2"
            )
        else:
            self.bot.send_message(
                chat_id, text,
                reply_markup=markup,
                parse_mode="MarkdownV2"
            )

    def _send_empty_events_message(self, chat_id: int,
                                   message_id: int = None) -> None: # Отправляет сообщение об отсутствии событий
        text = "У вас нет событий"
        if message_id:
            self.bot.edit_message_text(text, chat_id, message_id)
        else:
            self.bot.send_message(chat_id, text)

    def _send_error_message(self, chat_id: int, message_id: int = None,
                            text: str = "❌ Произошла ошибка") -> None: # Отправляет сообщение об ошибке
        if message_id:
            self.bot.edit_message_text(text, chat_id, message_id)
        else:
            self.bot.send_message(chat_id, text)

    def start_event_creation(self, user_id): # Начало создания события
        if user_id not in self.user_event_data:
            self.user_event_data[user_id] = {}
        return self.bm.get_year_menu()

    def _edit_message(self, call, text, reply_markup): # Редактирование сообщения ботом (функция для упрощения кода)
        self.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=reply_markup
        )

    def _update_event_list(self, call, user_id, success_text): # Обновление списка событий
        try:
            events = self.db.get_all_events(user_id)
            self.send_grouped_events(chat_id=call.message.chat.id, events=events, message_id=call.message.message_id)
            self.bot.answer_callback_query(call.id, success_text, show_alert=True)
        except Exception as e:
            self.logger.warning(f"[_update_event_list] Ошибка при обновлении списка событий : {e}")

    def _register_handlers(self): # Регистрация обработчиков
        try:
            self._register_time_handlers()
        except Exception as e:
            self.logger.error(f"Ошибка при регистрации обработчиков времени: {e}")
        try:
            self._register_edit_handlers()
        except Exception as e:
            self.logger.error(f"Ошибка при регистрации обработчиков редактирования: {e}")
        try:
            self._register_delete_handlers()
        except Exception as e:
            self.logger.error(f"Ошибка при регистрации обработчиков удаления: {e}")
        try:
            self._register_navigation_handlers()
        except Exception as e:
            self.logger.error(f"Ошибка при регистрации обработчиков навигации: {e}")
        try:
            self._register_other_handlers()
        except Exception as e:
            self.logger.error(f"Ошибка при регистрации других обработчиков: {e}")

    def _register_time_handlers(self): # Обработчики команд с временем событий
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("year_")) # Выбор года
        def handle_year_selection(call):
            user_id = call.message.chat.id
            try:
                selected_year = int(call.data.split("_")[1])
                self.user_event_data[user_id]['year'] = selected_year
                self._edit_message(call, f"Вы выбрали {selected_year} год. Теперь выберите месяц:",
                                   self.bm.get_month_menu())
            except Exception as e:
                self._handle_callback_error(call, "Ошибка выбора года", e)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('month_')) # Выбор месяца
        def handle_month_selection(call):
            user_id = call.message.chat.id
            try:
                selected_month = int(call.data.split('_')[1])
                self.user_event_data[user_id]['month'] = selected_month
                year = self.user_event_data[user_id].get('year', datetime.now().year)
                self._edit_message(call, f"Вы выбрали месяц: {selected_month}. Теперь выберите день:",
                                   self.bm.get_day_menu(selected_month, year))
            except Exception as e:
                self._handle_callback_error(call, "Ошибка выбора месяца", e)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('day_')) # Выбор дня
        def handle_day_selection(call):
            user_id = call.message.chat.id
            try:
                selected_day = int(call.data.split('_')[1])
                self.user_event_data[user_id]['day'] = selected_day
                self._edit_message(call, f"Вы выбрали день: {selected_day}. Теперь выберите время:",
                                   self.bm.get_time_menu())
            except Exception as e:
                self._handle_callback_error(call, "Ошибка выбора дня", e)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('time_')) # Выбор времени
        def handle_time_selection(call):
            user_id = call.message.chat.id
            try:
                selected = call.data.split('_')[1]

                if selected == 'allday':
                    self.user_event_data[user_id].update({'time': '08:00', 'all_day': 1})
                    text = "Вы выбрали: весь день. Хотите, чтобы событие повторялось?"
                elif selected == 'custom':
                    self.user_event_data[user_id]['awaiting_time'] = True
                    self.bot.send_message(user_id, "Введите время в формате ЧЧ:ММ (например, 09:30):")
                    return
                else:
                    self.user_event_data[user_id].update({'time': selected, 'all_day': 0})
                    text = f"Вы выбрали время: {selected}. Теперь выберите, за сколько времени напомнить:"

                self._edit_message(call, text, self.bm.get_reminder_offset_menu())
            except Exception as e:
                self._handle_callback_error(call, "Ошибка выбора времени", e)

        @self.bot.message_handler(func=lambda msg: self.user_event_data.get(
            msg.chat.id, {}).get('awaiting_time')) # Пользовательское время
        def process_custom_time(message):
            user_id = message.chat.id
            time_input = message.text.strip()

            try:
                datetime.strptime(time_input, "%H:%M")
                self.user_event_data[user_id].update({'time': time_input, 'awaiting_time': False, 'all_day': 0})
                self.bot.send_message(user_id,
                                      f"Вы установили время: {time_input}. Теперь выберите, за сколько времени напомнить:",
                                      reply_markup=self.bm.get_reminder_offset_menu())
            except ValueError:
                self.bot.send_message(user_id, "⛔ Неверный формат времени. Пожалуйста, введите в формате ЧЧ:ММ.")

    # ========== Обработчики удаления событий ==========
    def _register_delete_handlers(self):
        @self.bot.callback_query_handler(func=lambda call: call.data == "delete_mode") # Режим удаления
        def handle_delete_mode(call):
            try:
                user_id = call.from_user.id
                events = self.db.get_all_events(user_id)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при получении данных", e)

            try:
                if not events:
                    return self.bot.answer_callback_query(call.id, "Нет событий для удаления", show_alert=True)

                self.delete_state.selected_events[user_id] = set()
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при установке выбранных элементов для удаления", e)
            try:
                markup = self.bm.get_delete_menu(events)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при вызове меню удаления", e)
            try:
                self._edit_message(call, "🗑 Выберите события для удаления:", markup)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при входе в режим удаления", e)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("del_confirm")) # Подтверждение удаления
        def confirm_deletion(call):
            try:
                user_id = call.from_user.id
                selected_ids = self.delete_state.selected_events.get(user_id, set())
                if not selected_ids:
                    return self.bot.answer_callback_query(call.id, "Не выбрано ни одного события", show_alert=True)

                deleted_count = sum(self.db.delete_event(eid, user_id=user_id) for eid in selected_ids)
                self.delete_state.selected_events.pop(user_id, None)

                self._update_event_list(call, user_id, f"Удалено событий: {deleted_count}")
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при удалении", e)

        @self.bot.callback_query_handler(func=lambda call: call.data == "del_cancel") # Отмена удаления
        def cancel_deletion(call):
            try:
                user_id = call.from_user.id
                self.delete_state.selected_events.pop(user_id, None)
                self._update_event_list(call, user_id, "Удаление отменено")
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при отмене", e)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("del_toggle_")) # Выбор события для удаления
        def toggle_event_selection(call):
            try:
                user_id = call.from_user.id
                event_id = int(call.data.split("_")[2])
                selected = self.delete_state.selected_events.setdefault(user_id, set())
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при выборе объекта для удаления", e)
            try:
                if event_id in selected:
                    selected.remove(event_id)
                else:
                    selected.add(event_id)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при установке события для удаления", e)
            try:
                events = self.db.get_all_events(user_id)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при получении событий из БД", e)
            try:
                markup = self.bm.get_delete_menu(events, selected)
                self._edit_message(call, "🗑 Выберите события для удаления:", markup)
                self.bot.answer_callback_query(call.id)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка выбора события", e)

    # ========== Обработчики навигации в событиях ==========
    def _register_navigation_handlers(self):
        def send_event_page(chat_id, pages, page_num): # Отправка страницы событий
            try:
                markup = types.InlineKeyboardMarkup()
                current_page = pages[page_num]

                text = f"📅 Ваши события ({page_num * len(current_page) + 1}-{(page_num + 1) * len(current_page)} из {sum(len(p) for p in pages)})\n"
                text += "──────────────────\n"

                for event in current_page:
                    status = "🟢" if datetime.now() < event['datetime'] else "🔴"
                    text += f"{status} {event['day']}.{event['month']} {event['time']} - {event['description']}\n"

                buttons = self._get_navigation_buttons(page_num, pages)
                markup.row(*buttons)

                markup.row(
                    types.InlineKeyboardButton("🗑 Удалить", callback_data="delete_mode"),
                    types.InlineKeyboardButton("✏️ Редактировать", callback_data="events_edit")
                )

                self.bot.send_message(chat_id, text, reply_markup=markup)
            except Exception as e:
                self.logger.error(f"Error in send_event_page: {e}")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith(
            ("events_prev_", "events_next_"))) # Кнопки навигации "Дальше" и "Предыдущая"
        def handle_events_pagination(call):
            try:
                _, direction, page = call.data.split('_')
                page = int(page)
                new_page = page - 1 if direction == "prev" else page + 1
            except Exception as e:
                self.logger.warning(f"Ошибка при разметке страниц: {e}")

            try:
                events = self.db.get_all_events(call.from_user.id)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при получении событий", e)
            try:
                self.send_grouped_events(
                    chat_id=call.message.chat.id,
                    events=events,
                    page=new_page,
                    message_id=call.message.message_id
                )
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при отправке страницы", e)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("page_")) # Конкретная страницы событий
        def handle_pagination(call):
            page = int(call.data.split("_")[1])
            try:
                events = self.db.get_all_events(call.from_user.id)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при получении событий", e)
            try:
                self.send_grouped_events(
                    call.message.chat.id,
                    events,
                    page=page,
                    message_id=call.message.message_id
                )
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при отправке страницы", e)

        @self.bot.callback_query_handler(func=lambda call: call.data == "calendar_menu") # Возвращение в меню календаря
        def handle_back_to_menu(call):
            try:
                self._edit_message(call, "Вы вернулись в меню календаря", self.bm.get_calendar_menu())
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при возврате в меню", e)

        @self.bot.callback_query_handler(func=lambda call: call.data == "back_to_years") # Возвращение к выбору года
        def handle_back_to_years(call):
            try:
                user_id = call.from_user.id
                year = self.user_event_data[user_id].get('year', datetime.now().year)
                self._edit_message(call, "Выберите год:", self.bm.get_year_menu())
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при возврате к выбору года", e)

        @self.bot.callback_query_handler(func=lambda call: call.data == "back_to_months") # Возвращение к выбору месяца
        def handle_back_to_months(call):
            try:
                user_id = call.from_user.id
                year = self.user_event_data[user_id].get('year', datetime.now().year)
                self._edit_message(call, "Выберите месяц:", self.bm.get_month_menu())
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при возврате к выбору месяца", e)

    def _get_navigation_buttons(self, page_num, pages): # Создание кнопок навигации для "Мои события"
        try:
            buttons = []
            if page_num > 0:
                buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"events_prev_{page_num}"))

            buttons.append(types.InlineKeyboardButton(f"{page_num + 1}/{len(pages)}", callback_data="events_page"))

            if page_num < len(pages) - 1:
                buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"events_next_{page_num}"))

            return buttons
        except Exception as e:
            self.logger.warning(f"[_get_navigation_buttons] Ошибка при создании кнопок навигации: {e}")

    # ========== Обработчики редактирования событий ==========
    def _register_edit_handlers(self):
        @self.bot.callback_query_handler(func=lambda call: call.data == "edit_mode") # Режим редактирования
        def enter_edit_mode(call):
            try:
                events = self.db.get_all_events(call.from_user.id)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при получении событий", e)
            markup = types.InlineKeyboardMarkup()

            for event in events:
                btn_text = f"{event['day']}.{event['month']} {event.get('time', '')} - {event['event_description'][:15]}..."
                markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"edit_event_{event['id']}"))

            markup.row(
                types.InlineKeyboardButton("◀️ Назад", callback_data="cancel_edit")
            )

            self._edit_message(call, "Выберите событие для редактирования:", markup)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("edit_event_")) # Выбор параметра для редактирования
        def select_edit_field(call):
            event_id = call.data.split("_")[1]
            markup = types.InlineKeyboardMarkup()

            markup.row(
                types.InlineKeyboardButton("📅 Дата", callback_data=f"editevent_date_{event_id}"),
                types.InlineKeyboardButton("⏰ Время", callback_data=f"editevent_time_{event_id}")
            )
            markup.row(
                types.InlineKeyboardButton("📝 Текст", callback_data=f"editevent_text_{event_id}"),
                types.InlineKeyboardButton("🔄 Повтор", callback_data=f"editevent_repeat_{event_id}")
            )
            markup.row(
                types.InlineKeyboardButton("◀️ Назад", callback_data="edit_mode")
            )

            self._edit_message(call, "Что хотите изменить?", markup)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("editevent_text_")) # Редактирование описания
        def edit_event_text(call):
            try:
                event_id = call.data.split("_")[1]
                msg = self.bot.send_message(call.message.chat.id, "Введите новое описание события:")

                self.bot.register_next_step_handler(msg, process_new_text, event_id=event_id, original_call=call)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при редактировании события", e)

        def process_new_text(message, event_id, original_call): # Обновление описания события
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
                self._handle_callback_error(call, "Ошибка при запросе новой даты", e)
                self.bot.send_message(message.chat.id, "❌ Произошла ошибка")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("editevent_date_")) # Редактирование даты
        def edit_event_date(call):
            try:
                event_id = call.data.split("_")[1]
                msg = self.bot.send_message(call.message.chat.id, "Введите новую дату в формате ДД.ММ.ГГГГ:")
                self.bot.register_next_step_handler(msg, process_new_date, event_id=event_id, original_call=call)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при запросе новой даты", e)

        def process_new_date(message, event_id, original_call): # Обновление даты события
            try:
                new_date = message.text.strip()
                day, month, year = map(int, new_date.split("."))
                self.db.update_event_date(event_id, day, month, year)
                self.bot.send_message(message.chat.id, "📅 Дата обновлена.")
                self._update_event_list(original_call, message.chat.id, "Дата изменена.")
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при сохранении новой даты", e)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("editevent_time_")) # Редактирование времени
        def edit_event_time(call):
            try:
                event_id = call.data.split("_")[1]
                msg = self.bot.send_message(call.message.chat.id, "Введите новое время в формате ЧЧ:ММ:")
                self.bot.register_next_step_handler(msg, process_new_time, event_id=event_id, original_call=call)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при запросе нового времени", e)

        def process_new_time(message, event_id, original_call): # Обновление времени события
            try:
                new_time = message.text.strip()
                self.db.update_event_time(event_id, new_time)
                self.bot.send_message(message.chat.id, "⏰ Время обновлено.")
                self._update_event_list(original_call, message.chat.id, "Время изменено.")
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при сохранении нового времени", e)

        @self.bot.callback_query_handler(
            func=lambda call: call.data.startswith("editevent_repeat_")) # Редактирование повторения напоминания
        def edit_event_repeat(call):
            try:
                event_id = call.data.split("_")[1]
                markup = types.InlineKeyboardMarkup(row_width=2)
                options = [("⛔ Без повтора", "none"), ("📆 Каждый день", "daily"), ("📅 Каждую неделю", "weekly")]
                for text, value in options:
                    markup.add(types.InlineKeyboardButton(text, callback_data=f"setrepeat_{event_id}_{value}"))

                markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"edit_{event_id}"))
                self._edit_message(call, "Выберите тип повтора:", markup)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при выборе повтора", e)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("setrepeat_"))
        def set_event_repeat(call):
            try:
                _, event_id, repeat_type = call.data.split("_", 2)
                self.db.update_event_repeat(event_id, repeat_type)
                self.bot.answer_callback_query(call.id, "🔄 Повтор обновлен.")
                self._update_event_list(call, call.from_user.id, "Повтор изменен.")
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при установке повтора", e)

        @self.bot.callback_query_handler(func=lambda call: call.data == "cancel_edit") # Отмена редактирования
        def handle_cancel_edit(call):
            user_id = call.from_user.id
            try:
                events = self.db.get_all_events(user_id=user_id)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при получении событий", e)
            try:
                self._update_event_list(call, user_id, "Редактирование отменено")
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при вызове списка событий", e)

    # ========== Прочие обработчики событий ==========
    def _register_other_handlers(self):
        @self.bot.message_handler(func=lambda msg: 'напомни' in msg.text.lower()) # Обработчик для парсера сообщений
        def handle_reminder(message):
            user_id = message.from_user.id
            command = message.text.lower()

            try:
                event_data = self.parser.parse_event(command)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при разборе команды", e)
                return

            try:
                if not event_data:
                    self.bot.send_message(user_id, "Не удалось распознать дату или время для события.")
                    return

                if "date" not in event_data:
                    raise ValueError("Не найдена дата события")
            except Exception as e:
                self._handle_callback_error(call, "Ошибка с обязательными данными", e)
                return

            try:
                date_obj = event_data["date"]
                event_data["year"] = date_obj.year
                event_data["month"] = date_obj.month
                event_data["day"] = date_obj.day
                event_data["user_id"] = user_id
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при обработке даты", e)
                return

            try:
                event_id = self.db.save_event(
                    user_id=user_id,
                    year=event_data['year'],
                    month=event_data['month'],
                    day=event_data['day'],
                    time=event_data['time'],
                    event_description=event_data['event_description'],
                    all_day=event_data.get('all_day', 0),
                    repeat=event_data.get('repeat', 0),
                    reminder_offset=event_data.get('reminder_offset', 0)
                )
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при сохранении события", e)
                return

            try:
                if not event_id:
                    self.bot.send_message(user_id, "Не удалось сохранить событие.")
                    return

                event_data["id"] = event_id
                self.scheduler.schedule_event_reminder(event_data, user_id)
                self.bot.send_message(user_id, f"Событие создано: {event_data['event_description']}")
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при создании напоминания", e)

        def send_event_reminder(user_id, event_data):
            try:
                event_time = datetime(
                    year=event_data['date'].year,
                    month=event_data['date'].month,
                    day=event_data['date'].day,
                    hour=int(event_data['time'].split(':')[0]),
                    minute=int(event_data['time'].split(':')[1])
                )
                reminder_time = event_time - timedelta(minutes=event_data.get('reminder_offset', 0))

                time_left = event_data.get('reminder_offset', 0)
            except Exception as e:
                self.logger.error(f"[send_event_reminder] Ошибка при получении времени: {e}")

            try:
                time_str = "сейчас" if time_left == 0 else f"{time_left} мин."
                self.bot.send_message(
                    user_id,
                    f"🔔 Напоминание: {event_data['event_description']}\n"
                    f"⏰ Время события: {event_data['time']}\n"
                    f"⏳ До события осталось: {time_str}."
                )
            except Exception as e:
                self.logger.warning(f"[send_event_reminder] Ошибка при отправке сообщения пользователю: {e}")

        @self.bot.callback_query_handler(func=lambda call: call.data == ("add_reminder")) # Обработчик "Добавить событие"
        def handle_add_event(message):
            try:
                user_id = message.chat.id
                if user_id not in self.user_event_data:
                    self.user_event_data[user_id] = {}
                self.bot.send_message(user_id, "Выберите год:", reply_markup=self.bm.get_year_menu())
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при создании события", e)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('reminder_')) # За сколько напомнить
        def handle_reminder_offset_selection(call):
            user_id = call.message.chat.id
            try:
                offset = call.data.split('_')[1]
                if offset == 'none':
                    self.user_event_data[user_id]['reminder_offset'] = 0
                else:
                    self.user_event_data[user_id]['reminder_offset'] = int(offset)

                self._edit_message(call, "Хотите, чтобы событие повторялось ежедневно или было одноразовым?",
                                   self.bm.get_repeat_menu())
            except Exception as e:
                self._handle_callback_error(call, "Ошибка выбора напоминания", e)

        @self.bot.callback_query_handler(func=lambda call: call.data in ["repeat_daily", "repeat_once"]) # Ежедневное или одноразовое
        def handle_repeat_selection(call):
            user_id = call.message.chat.id
            try:
                self.user_event_data[user_id]['repeat'] = 1 if call.data == "repeat_daily" else 0
                self._edit_message(call, "✏️ Введите описание события:", None)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка выбора повторения", e)

        @self.bot.message_handler(
            func=lambda message: self.user_event_data.get(
                message.chat.id, {}).get('repeat') is not None) # Описание и сохранение события
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
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при сохранении события в БД", e)
                return

            try:
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
                self._handle_callback_error(message, "Системная ошибка при обработке события", e)