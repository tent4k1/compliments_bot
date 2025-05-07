import logging
import os

from datetime import datetime
from database import Database
from select import select
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telebot import TeleBot, types


class UserStates:
    def __init__(self):
        self.user_states = {}

    def set_state(self, user_id, state, data=None):
        """Устанавливаем состояние пользователя"""
        self.user_states[user_id] = {'state': state, 'data': data}

    def get_state(self, user_id):
        """Получаем текущее состояние пользователя"""
        return self.user_states.get(user_id, None)

    def clear_state(self, user_id):
        """Очищаем состояние пользователя"""
        if user_id in self.user_states:
            del self.user_states[user_id]

class List_Handlers:
    def __init__(self, bot, db, bm):
        self.bot = bot
        self.db = db
        self.bm = bm
        self.user_states = UserStates()
        self.logger = logging.getLogger(__name__)
        os.makedirs("images", exist_ok=True)

        self._register_handlers()

    def _handle_callback_error(self, call, message, exception): # Обработка ошибок
        self.logger.error(f"{message}: {exception}")
        self.bot.answer_callback_query(call.id, message)

    def _edit_message(self, call, text, reply_markup): # Редактирование сообщения ботом (функция для упрощения кода)
        self.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=reply_markup
        )

    def notify_partner_about_update(self, user_id, text):
        partner_id = self.db.get_partner(user_id)
        if partner_id:
            self.bot.send_message(partner_id, f"🔔 {text}")

    def process_partner_input(self, message):
        from_user_id = message.from_user.id
        input_text = message.text.strip()

        try:
            if input_text.startswith("@"):
                username = input_text[1:]
                partner_id = self.db.get_user_id_by_username(username)
                if not partner_id:
                    self.logger.warning(f"Пользователь с username @{username} не найден в базе данных.")
                    self.bot.send_message(from_user_id,
                                          "❗ Пользователь не найден. Убедитесь, что он запустил бота.")
                    return
            else:
                try:
                    partner_id = int(input_text)
                except ValueError:
                    self.bot.send_message(from_user_id, "⚠️ Неверный формат ID пользователя.")
                    return

            if from_user_id == partner_id:
                self.bot.send_message(from_user_id, "❗ Нельзя добавить самого себя в партнёры.")
                return
        except Exception as e:
            self.logger.warning(f"Ошибка при получении данных: {e}")
            return

        try:
            existing_partner = self.db.get_partner(from_user_id)
            if existing_partner:
                self.bot.send_message(from_user_id, "❗ У вас уже есть подтверждённый партнёр.")
                return
        except Exception as e:
            self.logger.warning(f"Ошибка при получении партнера из БД: {e}")
            return

        try:
            self.db.send_partner_request(from_user_id, partner_id)

            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Подтвердить партнёрство", callback_data=f"confirm_partner:{from_user_id}"))
            self.bot.send_message(partner_id,
                             f"👤 Пользователь {from_user_id} хочет добавить вас как партнёра.",
                             reply_markup=markup)
            self.bot.send_message(from_user_id, "📨 Запрос отправлен партнёру.")
        except Exception as e:
            self.logger.warning(f"Ошибка при добавлении партнёра: {e}")

    def process_list_name(self, message):
        user_id = message.from_user.id
        list_name = message.text.strip()
        if not list_name:
            self.bot.send_message(user_id, "❗ Название не может быть пустым.")
            return
        try:
            partner_id = self.db.get_partner(user_id)
        except Exception as e:
            self.logger.warning(f"⚠️ Ошибка при поолучении партнёра из БД: {e}")

        try:
            list_id = self.db.create_list(name=list_name, owner_id=user_id, partner_id=partner_id)
            self.bot.send_message(user_id, f"✅ Список «{list_name}» создан!", reply_markup=self.bm.get_lists_menu())
        except Exception as e:
            self.logger.warning(f"❗ Не удалось создать список. Попробуйте позже: {e}")

    def process_item_description(self, message, list_id):
        description = message.text
        markup = types.InlineKeyboardMarkup()
        self.user_states.set_state(message.from_user.id, 'awaiting_photo',
                                   {'list_id': list_id, 'description': description})

        markup.add(types.InlineKeyboardButton("❌ Без фото", callback_data=f"cancel_photo"))
        self.bot.send_message(message.chat.id,
                              "Теперь вы можете отправить фото или нажмите ❌ Без фото:", reply_markup=markup)
        self.bot.register_next_step_handler(message, self.process_optional_photo)

    def process_optional_photo(self, message):
        user_state = self.user_states.get_state(message.from_user.id)
        if user_state is None or user_state['state'] != 'awaiting_photo':
            return

        list_id = user_state['data']['list_id']
        description = user_state['data']['description']
        image_path = None

        if message.content_type == 'photo':
            file_info = self.bot.get_file(message.photo[-1].file_id)
            downloaded = self.bot.download_file(file_info.file_path)
            image_path = f"images/{datetime.now().strftime('%Y%m%d%H%M%S')}_{file_info.file_unique_id}.jpg"
            with open(image_path, 'wb') as f:
                f.write(downloaded)

        self.user_states.set_state(message.from_user.id, 'awaiting_date',
                                   {'list_id': list_id, 'description': description, 'image_path': image_path})

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌", callback_data=f"cancel_date"))
        self.bot.send_message(message.chat.id,
                              "Введите дату (ДД.ММ.ГГГГ) или ❌ Без даты, если не нужно:", reply_markup=markup)
        self.bot.register_next_step_handler(message, self.process_optional_date)

    def process_optional_date(self, message):
        user_state = self.user_states.get_state(message.from_user.id)
        if user_state is None or user_state['state'] != 'awaiting_date':
            return

        list_id = user_state['data']['list_id']
        description = user_state['data']['description']
        image_path = user_state['data']['image_path']
        due_date = None
        markup = types.InlineKeyboardMarkup()

        if message.text:
            try:
                due_date = datetime.strptime(message.text, "%d.%m.%Y").date().isoformat()
            except ValueError:
                markup.add(types.InlineKeyboardButton("❌ Без даты", callback_data=f"cancel_date"))
                self.bot.send_message(message.chat.id, "📅 Укажите дату или нажмите 'Без даты'", reply_markup=markup)
                return

        self.db.add_list_item(
            list_id=list_id,
            description=description,
            image_path=image_path,
            due_date=due_date,
            created_by=message.from_user.id
        )

        self.bot.send_message(message.chat.id, "Элемент добавлен ✅", reply_markup=self.bm.get_lists_menu())
        self.notify_partner_about_update(list_id, description, message.from_user.id)

        self.user_states.clear_state(message.from_user.id)

    def _register_handlers(self):
        try:
            self._register_partner_handlers()
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации обработчиков действий с партнером: {e}")

        try:
            self._register_edit_handlers()
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации обработчиков редактирования списков: {e}")

        try:
            self._register_other_handlers()
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации других обработчиков списков: {e}")

    def _register_partner_handlers(self):
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_partner:"))
        def handle_confirm_partner(call):
            partner_id = call.from_user.id
            requester_id = int(call.data.split(":")[1])

            if self.db.confirm_partner_request(requester_id, partner_id):
                self.bot.answer_callback_query(call.id, "Партнёрство подтверждено!")
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="🤝 Партнёрство подтверждено!"
                )

                self.bot.send_message(requester_id, "🎉 Ваш партнёр подтвердил заявку!")
            else:
                self.bot.answer_callback_query(call.id, "Ошибка подтверждения.")

        @self.bot.callback_query_handler(func=lambda call: call.data == "delete_partner_confirm")
        def confirm_partner_deletion(call):
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Да, удалить", callback_data="delete_partner_yes"),
                types.InlineKeyboardButton("↩️ Отмена", callback_data="delete_partner_cancel")
            )
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Вы уверены, что хотите удалить партнёра?",
                reply_markup=markup
            )

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("delete_partner_"))
        def handle_partner_deletion(call):
            user_id = call.from_user.id

            if call.data == "delete_partner_yes":
                success, partner_id = self.db.delete_partner(user_id)
                if success:
                    self.bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text="❌ Партнёр удалён."
                    )
                    if partner_id:
                        self.bot.send_message(
                            partner_id,
                            f"⚠️ Ваш партнёр @{call.from_user.username} удалил вас из списка партнёров."
                        )
                else:
                    self.bot.answer_callback_query(call.id, "Ошибка при удалении.")
            elif call.data == "delete_partner_cancel":
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Удаление отменено."
                )

    def _register_edit_handlers(self):
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("edit_list_"))
        def handle_edit_list(call):
            list_id = int(call.data.replace("edit_list_", ""))
            self.bot.answer_callback_query(call.id)

            items = self.db.get_list_items(list_id)
            if not items:
                self.bot.send_message(call.message.chat.id, "Список пуст.")
                return

            for item in items:
                text = f"📝 {item['description']}"
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_item_{item['id']}"),
                    InlineKeyboardButton("🗑 Удалить", callback_data=f"del_item_{item['id']}"),
                )
                self.bot.send_message(call.message.chat.id, text, reply_markup=markup)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("edit_item_"))
        def select_edititem_field(call):
            try:
                markup = types.InlineKeyboardMarkup()
                item_id = int(call.data.replace("edit_item_", ""))
            except Exception as e:
                self.logger.warning(f"[select_edititem_field] Ошибка при получении данных: {e}")

            markup.row(
                types.InlineKeyboardButton("📝 Текст", callback_data=f"edititem_text_{item_id}"),
                types.InlineKeyboardButton("📸 Фото", callback_data=f"edititem_photo_{item_id}")
            )
            markup.row(
                types.InlineKeyboardButton("📅 Дата", callback_data=f"edititem_date_{item_id}"),
                types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_lists")
            )
            self._edit_message(call, "Что хотите изменить?", markup)

        @self.bot.callback_query_handler(
            func=lambda call: call.data.startswith("edititem_text_"))  # Редактирование описания
        def edit_item_text(call):
            try:
                item_id = int(call.data.replace("edititem_text_", ""))
                msg = self.bot.send_message(call.message.chat.id, "Введите новое название элемента:")

                self.bot.register_next_step_handler(msg, process_new_text, item_id=item_id, original_call=call)
            except Exception as e:
                self.logger.warning(f"[edit_item_text] Ошибка при редактировании элемента списка: {e}")
                self.bot.send_message(message.chat.id, "Ошибка при редактировании элемента списка")

        def process_new_text(message, item_id, original_call):  # Обновление описания события
            try:
                new_text = message.text.strip()
                if not new_text:
                    self.bot.send_message(message.chat.id, "Текст не может быть пустым")
                    return

                if self.db.update_listitem_description(item_id, new_text):
                    self.bot.send_message(message.chat.id, "Описание обновлено ✅")

                    user_id = message.from_user.id
                    lists = self.db.get_user_lists(user_id)
                else:
                    self.bot.send_message(message.chat.id, "❌ Ошибка обновления")
            except Exception as e:
                self.logger.warning(f"[process_new_text] Ошибка при обновлении текста элемента списка: {e}")
                self.bot.send_message(message.chat.id, "❌ Произошла ошибка")

            try:
                user_id = message.from_user.id
                self.notify_partner_about_update(user_id, f"Название элемента было обновлено на {new_text}")
            except Exception as e:
                self.logger.warning(f"[process_new_text] Ошибка при уведомлении партнера об изменении названия: {e}")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("edititem_date_"))
        def edit_item_date(call):
            try:
                item_id = int(call.data.replace("edititem_date_", ""))
                msg = self.bot.send_message(call.message.chat.id, "Введите новую дату в формате ДД.ММ.ГГГГ:")
                self.bot.register_next_step_handler(msg, process_new_date, item_id, call)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при редактировании даты элемента списка", e)

        def process_new_date(message, item_id, original_call):
            try:
                new_date = datetime.strptime(message.text, "%d.%m.%Y").date().isoformat()
                self.db.update_item_date(new_date, item_id)
                self.bot.send_message(message.chat.id, "📅 Дата обновлена.")
            except Exception as e:
                self.logger.warning(f"[process_new_date] Ошибка при редактировании даты элемента списка: {e}")
                self.bot.send_message(message.chat.id, "❌ Произошла ошибка при сохранении даты")

            try:
                user_id = message.from_user.id
                date_text = datetime.strptime(new_date, "%Y-%m-%d").strftime("%d.%m.%Y")
                self.notify_partner_about_update(user_id, f"Дата элемента была обновлена на {date_text}")
            except Exception as e:
                self.logger.warning(f"[process_new_text] Ошибка при уведомлении партнера об изменении даты: {e}")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("edititem_photo_"))
        def edit_item_photo(call):
            try:
                item_id = int(call.data.replace("edititem_photo_", ""))
                msg = self.bot.send_message(call.message.chat.id, "📷 Отправьте новое фото:")
                self.bot.register_next_step_handler(msg, process_new_photo, item_id, call)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при редактировании фото", e)

        def process_new_photo(message, item_id, original_call):
            try:
                if message.content_type != 'photo':
                    self.bot.send_message(message.chat.id, "❌ Пожалуйста, отправьте изображение.")
                    return

                file_info = self.bot.get_file(message.photo[-1].file_id)
                downloaded = self.bot.download_file(file_info.file_path)
                image_path = f"images/{datetime.now().strftime('%Y%m%d%H%M%S')}_{file_info.file_unique_id}.jpg"
                with open(image_path, 'wb') as f:
                    f.write(downloaded)

                self.db.update_item_photo(item_id, image_path)
                self.bot.send_message(message.chat.id, "📷 Фото обновлено.")

                user_id = message.from_user.id
                self.notify_partner_about_update(user_id, "Фото элемента было обновлено.")
            except Exception as e:
                self.logger.warning(f"[process_new_photo] Ошибка при обновлении фото: {e}")
                self.bot.send_message(message.chat.id, "❌ Произошла ошибка при сохранении фото")

    def _register_other_handlers(self):
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("view_list_"))
        def handle_view_list(call):
            list_id = int(call.data.replace("view_list_", ""))
            user_id = call.from_user.id
            self.bot.answer_callback_query(call.id)

            items = self.db.get_list_items(list_id)
            if not items:
                self.bot.send_message(call.message.chat.id, "📝 Список пуст.")
                return

            message_lines = [f"📋 <b>Список:</b>"]
            photo_items = []

            for idx, item in enumerate(items, start=1):
                line = f"\n<b>{idx}. {item['description']}</b>"
                if item['due_date']:
                    line += f"\n📅 <i>До:</i> {item['due_date']}"
                message_lines.append(line)

                if item.get('image_path'):
                    photo_items.append(item)

            full_message = "\n".join(message_lines)
            self.bot.send_message(call.message.chat.id, full_message, parse_mode="HTML")

            for item in photo_items:
                text = f"📌 {item['description']}"
                if item['due_date']:
                    text += f"\n📅 До: {item['due_date']}"

                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton("✏️", callback_data=f"edit_item_{item['id']}"),
                    types.InlineKeyboardButton("❌", callback_data=f"del_item_{item['id']}")
                )

                try:
                    with open(item['image_path'], 'rb') as photo:
                        self.bot.send_photo(call.message.chat.id, photo, caption=text, reply_markup=markup)
                except Exception as e:
                    self.logger.warning(f"Ошибка при загрузке фото {item['image_path']}: {e}")

            action_markup = types.InlineKeyboardMarkup(row_width=2)
            action_markup.add(
                types.InlineKeyboardButton("➕ Добавить элемент", callback_data=f"additem_list_{list_id}"),
                types.InlineKeyboardButton("✏️ Редактировать список", callback_data=f"edit_list_{list_id}"),
                types.InlineKeyboardButton("❌ Удалить список", callback_data=f"delete_list_{list_id}"),
                types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_lists")
            )
            self.bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=action_markup)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("additem_list_"))
        def handle_list_selection(call):
            list_id = int(call.data.replace("additem_list_", ""))
            self.bot.answer_callback_query(call.id)

            msg = self.bot.send_message(call.message.chat.id, "Введите описание элемента:")
            self.bot.register_next_step_handler(msg, self.process_item_description, list_id)

        @self.bot.callback_query_handler(func=lambda call: call.data == "back_to_lists")
        def back_to_lists(call):
            user_id = call.from_user.id
            lists = self.db.get_user_lists(user_id)

            if not lists:
                self.bot.send_message(user_id, "❗ У вас пока нет списков.")
                return

            markup = types.InlineKeyboardMarkup()
            for lst in lists:
                markup.add(types.InlineKeyboardButton(lst['name'], callback_data=f"view_list_{lst['id']}"))

            self.bot.send_message(user_id, "📋 Ваши списки:", reply_markup=markup)

        @self.bot.callback_query_handler(func=lambda call: call.data == ("cancel_photo"))
        def handle_cancel_photo(call):
            self.bot.answer_callback_query(call.id)
            markup = types.InlineKeyboardMarkup()

            user_state = self.user_states.get_state(call.from_user.id)
            if user_state and user_state['state'] == 'awaiting_photo':
                list_id = user_state['data']['list_id']
                description = user_state['data']['description']
                self.user_states.set_state(call.from_user.id, 'awaiting_date', {'list_id': list_id, 'description': description, 'image_path': None})

                markup.add(types.InlineKeyboardButton("❌ Без даты", callback_data=f"cancel_date"))
                self.bot.send_message(call.message.chat.id,
                                      "Введите дату (ДД.ММ.ГГГГ) или ❌ Без даты", reply_markup=markup)
                self.bot.register_next_step_handler(call.message, self.process_optional_date)

        @self.bot.callback_query_handler(func=lambda call: call.data == ("cancel_date"))
        def handle_cancel_date(call):
            self.bot.answer_callback_query(call.id)

            user_state = self.user_states.get_state(call.from_user.id)
            if user_state and user_state['state'] == 'awaiting_date':
                list_id = user_state['data']['list_id']
                description = user_state['data']['description']
                image_path = user_state['data']['image_path']

                self.db.add_list_item(
                    list_id=list_id,
                    description=description,
                    image_path=image_path,
                    due_date=None,
                    created_by=call.from_user.id
                )
                self.bot.send_message(call.message.chat.id, "Элемент добавлен без даты ✅", reply_markup=self.bm.get_lists_menu())
                self.notify_partner_about_update(list_id, description, call.from_user.id)

                self.user_states.clear_state(call.from_user.id)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("delete_list_"))
        def handle_delete_list(call):
            list_id = int(call.data.replace("delete_list_", ""))
            self.db.delete_list(list_id)
            self.bot.answer_callback_query(call.id, "Список удалён.")
            self.bot.send_message(call.message.chat.id, "Список удалён ❌")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("del_item_"))
        def delete_list_item(call):
            item_id = int(call.data.replace("del_item_", ""))
            user_id = call.from_user.id

            self.db.delete_list_item(item_id)
            self.notify_partner_about_update(user_id, "Партнёр удалил элемент из общего списка.")
            self.bot.answer_callback_query(call.id, "Элемент удалён.")
            self.bot.edit_message_text("❌ Элемент удалён", chat_id=call.message.chat.id,
                                       message_id=call.message.message_id)