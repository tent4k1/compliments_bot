import logging
import os

from datetime import datetime, timedelta
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

    def _handle_callback_error(self, call, message, exception):
        """Обработка ошибок"""
        self.logger.error(f"{message}: {exception}")
        self.bot.answer_callback_query(call.id, message)

    def _edit_message(self, call, text, reply_markup):
        """Редактирование сообщения ботом (функция для упрощения кода)"""
        self.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=reply_markup
        )

    def notify_partner_about_update(self, user_id, msg, list_name, text=None):
        """Оповещение партнера об операции со списком"""
        partner_id = self.db.get_partner(user_id)
        if partner_id:
            if text:
                self.bot.send_message(partner_id, f"🔔 {msg}{text}, список - '{list_name}'")
            else:
                self.bot.send_message(partner_id, f"🔔 {msg} список - '{list_name}'")

    def process_partner_input(self, message):
        """Обрабатывает ввод пользователя для добавления партнера"""
        from_user_id = message.from_user.id
        input_text = message.text.strip()

        partner_id = self._validate_and_get_partner_id(from_user_id, input_text)
        if not partner_id:
            return

        if not self._check_partner_conditions(from_user_id, partner_id):
            return

        self._send_partner_request(from_user_id, partner_id)

    def _validate_and_get_partner_id(self, from_user_id, input_text):
        """Валидирует ввод и возвращает ID партнера или None"""
        if input_text.startswith("@"):
            username = input_text[1:]
            partner_id = self.db.get_user_id_by_username(username)
            if not partner_id:
                self._send_user_not_found(from_user_id, username)
                return None
        else:
            try:
                partner_id = int(input_text)
            except ValueError:
                self.bot.send_message(from_user_id, "⚠️ Неверный формат ID пользователя.")
                return None

        if from_user_id == partner_id:
            self.bot.send_message(from_user_id, "❗ Нельзя добавить самого себя в партнёры.")
            return None

        return partner_id

    def _send_user_not_found(self, user_id, username):
        """Отправляет сообщение о ненайденном пользователе"""
        self.logger.warning(f"Пользователь с username @{username} не найден")
        self.bot.send_message(user_id, "❗ Пользователь не найден. Убедитесь, что он запустил бота.")

    def _check_partner_conditions(self, from_user_id, partner_id):
        """Проверяет все условия для отправки запроса"""
        try:
            if self.db.get_partner(from_user_id):
                self.bot.send_message(from_user_id, "❗ У вас уже есть подтверждённый партнёр.")
                return False

            if self.db.has_pending_request(from_user_id, partner_id):
                self.bot.send_message(from_user_id,
                                      "❗ У вас уже есть активный запрос на партнёрство.")
                return False

            last_request_time = self.db.get_last_request_time(from_user_id, partner_id)
            if last_request_time:
                time_diff = datetime.now() - datetime.strptime(last_request_time, "%Y-%m-%d %H:%M:%S")
                if time_diff < timedelta(hours=24):
                    hours_left = 24 - time_diff.total_seconds() // 3600
                    self.bot.send_message(from_user_id,
                                          f"❗ Повторный запрос возможен через {hours_left:.0f} часов.")
                    return False

        except Exception as e:
            self.logger.error(f"Ошибка проверки условий партнерства: {e}")
            self.bot.send_message(from_user_id, "❌ Ошибка при проверке данных")
            return False

        return True

    def _send_partner_request(self, from_user_id, partner_id):
        """Отправляет запрос на партнерство"""
        try:
            self.db.send_partner_request(from_user_id, partner_id)
            username = self.db.get_username_by_user_id(from_user_id)

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "✅ Подтвердить партнёрство",
                callback_data=f"confirm_partner:{from_user_id}"
            ))

            self.bot.send_message(
                partner_id,
                f"👤 Пользователь {username} хочет добавить вас как партнёра.",
                reply_markup=markup
            )
            self.bot.send_message(from_user_id, "📨 Запрос отправлен партнёру.")

        except Exception as e:
            self.logger.error(f"Ошибка отправки запроса партнерства: {e}")
            self.bot.send_message(from_user_id, "❌ Не удалось отправить запрос")

    def process_list_name(self, message):
        """Обработка ввода названия списка"""
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
        """Обработка ввода названия элемента списка"""
        description = message.text
        markup = types.InlineKeyboardMarkup()
        self.user_states.set_state(message.from_user.id, 'awaiting_photo',
                                   {'list_id': list_id, 'description': description})

        markup.add(types.InlineKeyboardButton("❌ Без фото", callback_data=f"cancel_photo"))
        self.bot.send_message(message.chat.id,
                              "Теперь вы можете отправить фото или нажмите ❌ Без фото:", reply_markup=markup)
        self.bot.register_next_step_handler(message, self.process_optional_photo)

    def process_optional_photo(self, message):
        """Обработка отправки фото для элемента списка"""
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
        """Обработка ввода даты для элемента списка"""
        user_state = self.user_states.get_state(message.from_user.id)
        if user_state is None or user_state['state'] != 'awaiting_date':
            return

        list_id = user_state['data']['list_id']
        description = user_state['data']['description']
        image_path = user_state['data']['image_path']
        list_name = self.db.get_listtitle_by_id(list_id)
        due_date = None

        if message.text:
            try:
                due_date = datetime.strptime(message.text, "%d.%m.%Y").date().isoformat()
            except ValueError:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ Без даты", callback_data=f"cancel_date"))
                self.bot.send_message(message.chat.id,
                                      "⚠️ Неверный формат. Введите дату в формате ДД.ММ.ГГГГ или нажмите 'Без даты'.",
                                      reply_markup=markup)
                self.bot.register_next_step_handler(message, self.process_optional_date)
                return

        self.db.add_list_item(
            list_id=list_id,
            description=description,
            image_path=image_path,
            due_date=due_date,
            created_by=message.from_user.id
        )
        msg = f"Ваш партнер добавил новый элемент в список:"
        self.bot.send_message(message.chat.id, "Элемент добавлен ✅", reply_markup=self.bm.get_lists_menu())
        self.notify_partner_about_update(message.from_user.id,
                                         f"Ваш партнер добавил новый элемент {description} в список:", list_name)

        self.user_states.clear_state(message.from_user.id)

    def _generate_list_message(self, items):
        """Генерирует текст сообщения со списком элементов"""
        message_lines = ["📋 <b>Список:</b>"]
        for idx, item in enumerate(items, start=1):
            line = f"\n<b>{idx}. {item['description']}</b>"
            if item['due_date']:
                line += f"\n📅 <i>До:</i> {item['due_date']}"
            message_lines.append(line)
        return "\n".join(message_lines)

    def _send_items_with_photos(self, chat_id, items):
        """Отправляет элементы с прикрепленными фото"""
        for item in items:
            if not item.get('image_path'):
                continue

            text = f"📌 {item['description']}"
            if item['due_date']:
                text += f"\n📅 До: {item['due_date']}"

            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton("✏️", callback_data=f"edit_item_{item['id']}"),
                types.InlineKeyboardButton("❌", callback_data=f"del_item_{item['id']}")
            )

            try:
                with open(item['image_path'], 'rb') as photo:
                    self.bot.send_photo(chat_id, photo, caption=text, reply_markup=markup)
            except Exception as e:
                self.logger.error(f"Ошибка загрузки фото: {item['image_path']}. Ошибка: {e}")

    def _show_empty_list_interface(self, chat_id, list_id):
        """Показывает интерфейс для пустого списка"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ Добавить элемент", callback_data=f"additem_list_{list_id}"),
            types.InlineKeyboardButton("✏️ Редактировать список", callback_data=f"edit_list_{list_id}"),
            types.InlineKeyboardButton("❌ Удалить список", callback_data=f"delete_list_{list_id}"),
            types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_lists")
        )
        self.bot.send_message(chat_id, "📝 Список пуст.", reply_markup=markup)

    def _show_list_management_interface(self, chat_id, list_id):
        """Показывает интерфейс управления списком"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ Добавить элемент", callback_data=f"additem_list_{list_id}"),
            types.InlineKeyboardButton("✏️ Редактировать список", callback_data=f"edit_list_{list_id}"),
            types.InlineKeyboardButton("❌ Удалить список", callback_data=f"delete_list_{list_id}"),
            types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_lists")
        )
        self.bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

    def _register_handlers(self):
        """Регистрация обработчиков действий со списками"""
        try:
            self._register_partner_handlers()
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации обработчиков действий с партнером: {e}")

        try:
            self._register_delete_handlers()
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации обработчиков удаления: {e}")

        try:
            self._register_edit_handlers()
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации обработчиков редактирования списков: {e}")

        try:
            self._register_other_handlers()
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации других обработчиков списков: {e}")

    def _register_partner_handlers(self):
        """Обработчики действий с партнером"""
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_partner:"))
        def handle_confirm_partner(call):
            """Подтверждение заявки на партнерство"""
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
            """Подтверждение удаления партнера"""
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
            """Удаление партнера с подтверждением"""
            user_id = call.from_user.id

            if call.data == "delete_partner_cancel":
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Удаление отменено."
                )
                return

            if call.data != "delete_partner_yes":
                self.logger.warning(f"Неизвестное действие: {call.data}")
                return

            success, partner_id = self.db.delete_partner(user_id)
            if not success:
                self.bot.answer_callback_query(call.id, "Ошибка при удалении")
                return

            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="❌ Партнёр удалён."
            )

            if partner_id:
                username = self.db.get_username_by_user_id(user_id)
                self.bot.send_message(
                    partner_id,
                    f"⚠️ Ваш партнёр @{username} удалил вас из списка партнёров."
                )

    def _register_edit_handlers(self):
        """Обработчики, отвечающие за редактирование в списках"""
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("edit_list_"))
        def handle_edit_list(call):
            list_id = int(call.data.replace("edit_list_", ""))
            self.bot.answer_callback_query(call.id)

            try:
                items = self.db.get_list_items(list_id)
            except Exception as e:
                self.logger.warning(f"[handle_edit_list] Ошибка при получении элементов списка из БД: {e}")
                self.bot.send_message(call.message.chat.id, "❌ Ошибка при получении элементов списка")
                return False

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
            """Режим редактирования элемента списка пользователя"""
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
            func=lambda call: call.data.startswith("edititem_text_"))
        def edit_item_text(call):
            """Редактирование описания элемента списка пользователя"""
            try:
                item_id = int(call.data.replace("edititem_text_", ""))
                msg = self.bot.send_message(call.message.chat.id, "Введите новое название элемента:")

                self.bot.register_next_step_handler(msg, process_new_text, item_id=item_id, original_call=call)
            except Exception as e:
                self.logger.warning(f"[edit_item_text] Ошибка при редактировании элемента списка: {e}")
                self.bot.send_message(message.chat.id, "Ошибка при редактировании элемента списка")

        def process_new_text(message, item_id, original_call):
            """Обновление описания элемента списка пользователя"""
            try:
                new_text = message.text.strip()
                list_id = self.db.get_listID_by_itemid(item_id)
                list_name = self.db.get_listtitle_by_id(list_id)
            except Exception as e:
                self.logger.warning(f"[process_new_text] Ошибка при получении данных для обновления списка: {e}")
                self.bot.send_message(message.chat.id, "❌ Произошла ошибка")

            try:
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
                msg = "Название элемента было обновлено на "
                self.notify_partner_about_update(user_id, msg, list_name, new_text)
            except Exception as e:
                self.logger.warning(f"[process_new_text] Ошибка при уведомлении партнера об изменении названия: {e}")
                self.bot.send_message(message.chat.id, "⚠️ Не удается оповестить партнера об изменении")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("edititem_date_"))
        def edit_item_date(call):
            """Редактирование даты элемента списка пользователя"""
            try:
                item_id = int(call.data.replace("edititem_date_", ""))
                msg = self.bot.send_message(call.message.chat.id, "Введите новую дату в формате ДД.ММ.ГГГГ:")
                self.bot.register_next_step_handler(msg, process_new_date, item_id, call)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при редактировании даты элемента списка", e)

        def process_new_date(message, item_id, original_call):
            """Обновление даты элемента списка пользователя"""
            try:
                new_date = datetime.strptime(message.text, "%d.%m.%Y").date().isoformat()
                self.db.update_item_date(new_date, item_id)
                self.bot.send_message(message.chat.id, "📅 Дата обновлена.")
            except Exception as e:
                self.logger.warning(f"[process_new_date] Ошибка при редактировании даты элемента списка: {e}")
                self.bot.send_message(message.chat.id, "❌ Произошла ошибка при сохранении даты")

            try:
                item_name = self.db.get_itemname_by_id(item_id)
                list_id = self.db.get_listID_by_itemid(item_id)
                list_name = self.db.get_listtitle_by_id(list_id)
                user_id = message.from_user.id
                date_text = datetime.strptime(new_date, "%Y-%m-%d").strftime("%d.%m.%Y")
                msg = f"Дата элемента {item_name} была обновлена на: "
                self.notify_partner_about_update(user_id, msg, list_name, date_text)
            except Exception as e:
                self.logger.warning(f"[process_new_text] Ошибка при уведомлении партнера об изменении даты: {e}")
                self.bot.send_message(message.chat.id, "⚠️ Не удается оповестить партнера об изменении")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("edititem_photo_"))
        def edit_item_photo(call):
            """Редактирование фото элемента списка пользователя"""
            try:
                item_id = int(call.data.replace("edititem_photo_", ""))
                msg = self.bot.send_message(call.message.chat.id, "📷 Отправьте новое фото:")
                self.bot.register_next_step_handler(msg, process_new_photo, item_id, call)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при редактировании фото", e)

        def process_new_photo(message, item_id, original_call):
            """Обновление фото элемента списка пользователя"""
            try:
                if message.content_type != 'photo':
                    self.bot.send_message(message.chat.id, "❌ Пожалуйста, отправьте изображение.")
                    return

                file_info = self.bot.get_file(message.photo[-1].file_id)
                downloaded = self.bot.download_file(file_info.file_path)
                image_path = f"images/{datetime.now().strftime('%Y%m%d%H%M%S')}_{file_info.file_unique_id}.jpg"
                with open(image_path, 'wb') as f:
                    f.write(downloaded)
            except Exception as e:
                self.logger.warning(f"[process_new_photo] Ошибка при сохранении фото: {e}")
                self.bot.send_message(message.chat.id, "❌ Произошла ошибка при сохранении фото")

            try:
                self.db.update_item_photo(item_id, image_path)
                self.bot.send_message(message.chat.id, "📷 Фото обновлено.")
            except Exception as e:
                self.logger.warning(f"[process_new_photo] Ошибка при обновлении пути к фото в БД: {e}")
                self.bot.send_message(message.chat.id, "❌ Произошла ошибка при сохранении фото")

            try:
                item_name = self.db.get_itemname_by_id(item_id)
                list_id = self.db.get_listID_by_itemid(item_id)
                list_name = self.db.get_listtitle_by_id(list_id)
                user_id = message.from_user.id
            except Exception as e:
                self.logger.warning(f"[process_new_photo] Ошибка при получении данных из БД для оповещения: {e}")

            try:
                self.notify_partner_about_update(user_id, f"Фото элемента {item_name} было обновлено", list_name)
            except Exception as e:
                self.logger.warning(f"[process_new_photo] Ошибка при оповещении партнера: {e}")
                self.bot.send_message(message.chat.id, "⚠️ Не удается оповестить партнера об изменении")

    def _register_delete_handlers(self):
        """Обработчики удаления списков и их элементов"""
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("delete_list_"))
        def handle_delete_list(call):
            """Удаление списка пользователя"""
            try:
                list_id = int(call.data.replace("delete_list_", ""))
                list_name = self.db.get_listtitle_by_id(list_id)
                user_id = call.from_user.id
                self.db.delete_list(list_id)
            except Exception as e:
                self._handle_callback_error(call, "Ошибка при удалении списка", e)

            try:
                self.notify_partner_about_update(user_id, "Партнёр удалил общий список: ", list_name)
                self.bot.answer_callback_query(call.id, "Список удалён.")
                self.bot.send_message(call.message.chat.id, "Список удалён ❌")
            except Exception as e:
                self._handle_callback_error(call, "⚠️ Не удается оповестить партнера об изменении", e)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("del_item_"))
        def delete_list_item(call):
            """Удаление элемента списка пользователя"""
            try:
                item_id = int(call.data.replace("del_item_", ""))
                item_name = self.db.get_itemname_by_id(item_id)
                list_id = self.db.get_listID_by_itemid(item_id)
                list_name = self.db.get_listtitle_by_id(list_id)
                user_id = call.from_user.id
            except Exception as e:
                self.logger.warning(f"[delete_list_item] Ошибка при получении данных о списке: {e}")

            try:
                self.db.delete_list_item(item_id)
            except Exception as e:
                self.logger.warning(f"[delete_list_item] Ошибка при удалении списка: {e}")

            try:
                self.notify_partner_about_update(user_id,
                                                 "Партнёр удалил элемент из общего списка: ", list_name, item_name)
                self.bot.answer_callback_query(call.id, "Элемент удалён.")
                self.bot.edit_message_text("❌ Элемент удалён", chat_id=call.message.chat.id,
                                           message_id=call.message.message_id)
            except Exception as e:
                self.logger.warning(f"[delete_list_item] Ошибка при оповещении партнера: {e}")
                self.bot.send_message(message.chat.id, "⚠️ Не удается оповестить партнера об изменении")

    def _register_other_handlers(self):
        """Иные обработчики списков"""
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("view_list_"))
        def handle_view_list(call):
            """Отображает список элементов с возможностью управления"""
            list_id = int(call.data.replace("view_list_", ""))
            user_id = call.from_user.id
            self.bot.answer_callback_query(call.id)

            items = self.db.get_list_items(list_id)

            if not items:
                self._show_empty_list_interface(call.message.chat.id, list_id)
                return

            message_text = self._generate_list_message(items)
            self.bot.send_message(call.message.chat.id, message_text, parse_mode="HTML")

            self._send_items_with_photos(call.message.chat.id, items)

            self._show_list_management_interface(call.message.chat.id, list_id)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("additem_list_"))
        def handle_add_item(call):
            """Добавление элемента в список пользователя"""
            list_id = int(call.data.replace("additem_list_", ""))
            self.bot.answer_callback_query(call.id)

            msg = self.bot.send_message(call.message.chat.id, "Введите описание элемента:")
            self.bot.register_next_step_handler(msg, self.process_item_description, list_id)

        @self.bot.callback_query_handler(func=lambda call: call.data == "back_to_lists")
        def back_to_lists(call):
            """Вернуться обратно к спискам пользователя"""
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
            """Выбор 'Без фото' при добавлении элемента"""
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
            """Выбор 'Без даты' при добавлении элемента"""
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
                list_name = self.db.get_listtitle_by_id(list_id)
                self.bot.send_message(call.message.chat.id, "Элемент добавлен без даты ✅", reply_markup=self.bm.get_lists_menu())
                self.notify_partner_about_update(call.from_user.id, f"Партнёр добавил: {description}", list_name)

                self.user_states.clear_state(call.from_user.id)