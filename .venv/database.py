import sqlite3
import threading
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Set, Any
from pydantic.v1.utils import sequence_like

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('database.log'),
        logging.StreamHandler()
    ]
)
logging.basicConfig(level=logging.DEBUG)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

class Database:
    _instance = None
    _lock = threading.Lock()
    DB_VERSION = 3

    def __new__(cls):
        """Реализация Singleton для единственного подключения к БД"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize_db()
        return cls._instance

    def _initialize_db(self):
        """Инициализация базы данных"""
        self.db_path = Path('data') / 'bot_database.db'
        self._ensure_data_dir()

        self.conn = sqlite3.connect(
            str(self.db_path),
            timeout=20,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

        self._create_tables()
        self._check_migrations()

        logger.info(f"БД инициалиирована в: {self.db_path}")

    def _ensure_data_dir(self):
        """Создание папки data если не существует"""
        try:
            Path('data').mkdir(exist_ok=True)
        except Exception as e:
            logger.error(f"[_ensure_data_dir] Ошибка при создании директории: {e}")
            raise

    def _create_tables(self):
        """Создание таблиц базы данных с актуальной схемой"""
        tables = [
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language_code TEXT DEFAULT NULL,
                is_subscribed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS compliments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT UNIQUE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sent_compliments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                compliment_id INTEGER,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(compliment_id) REFERENCES compliments(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS wishlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                wish_text TEXT NOT NULL,
                is_fulfilled BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fulfilled_at TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS db_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version INTEGER PRIMARY KEY
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sent_compliments_user ON sent_compliments(user_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sent_compliments_time ON sent_compliments(sent_at)
            """,
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                year INTEGER DEFAULT 2025,
                month TEXT,
                day INTEGER,
                time TEXT,
                event_description TEXT,
                all_day INTEGER DEFAULT 0,
                repeat INTEGER DEFAULT 0,
                reminder_offset INTEGER DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS partners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requester_id INTEGER,
                partner_id INTEGER,
                confirmed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (requester_id) REFERENCES users(user_id),
                FOREIGN KEY (partner_id) REFERENCES users(user_id)
            )
            """,
            """
           CREATE TABLE IF NOT EXISTS lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                owner_id INTEGER,
                partner_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(user_id),
                FOREIGN KEY (partner_id) REFERENCES users(user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS list_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_id INTEGER,
                description TEXT NOT NULL,
                image_path TEXT,
                due_date TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (list_id) REFERENCES lists(id),
                FOREIGN KEY (created_by) REFERENCES users(user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                read INTEGER DEFAULT 0
            )
            """
        ]

        try:
            with self.conn:
                for table in tables:
                    self.conn.execute(table)
                self.conn.execute("INSERT OR IGNORE INTO db_meta (version) VALUES (?)", (self.DB_VERSION,))
            logger.info("Таблицы БД созданы/прошли проверку")
        except Exception as e:
            logger.error(f"[_create_tables] Ошибка при создании таблиц: {e}")
            raise

    def _check_migrations(self):
        """Проверка миграций БД"""
        try:
            cursor = self.conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_meta'")
            if not cursor.fetchone():
                self.conn.execute("""
                CREATE TABLE db_meta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version INTEGER UNIQUE
                )
                """)
                current_version = 0
            else:
                cursor.execute("SELECT version FROM db_meta LIMIT 1")
                result = cursor.fetchone()
                current_version = result[0] if result else 0

            for version in range(current_version + 1, self.DB_VERSION + 1):
                migration_method = getattr(self, f"_migrate_v{version}", None)
                if migration_method:
                    migration_method()
                    with self.conn:
                        cursor.execute("DELETE FROM db_meta")
                        cursor.execute("INSERT INTO db_meta (version) VALUES (?)", (version,))
                    logger.info(f"БД успешно мигрировала на версию: {version}")

        except Exception as e:
            logger.error(f"[_check_migrations] Ошибка при миграции таблицы: {e}")
            raise

    def _migrate_v1(self):
        """Миграция на версию 1: добавление language_code и last_active"""
        with self.conn:
            cursor = self.conn.cursor()

            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]

            if 'language_code' not in columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN language_code TEXT DEFAULT NULL")
                logger.info("Добавлен language_code колонка для users таблицы")

            if 'last_active' not in columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                logger.info("Добавлена last_active колонка для users таблицы")

    def _migrate_v2(self):
        """Миграция на версию 2: добавление таблицы db_meta"""
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_meta'")
            if not cursor.fetchone():
                self.conn.execute("""
                CREATE TABLE db_meta (
                    version INTEGER PRIMARY KEY
                )
                """)
                self.conn.execute("INSERT INTO db_meta (version) VALUES (2)")
                logger.info("Добавлена db_meta таблица")

    def _migrate_v3(self):
        """Миграция на версию 3: доюавление столбца reminder_offset в таблицу events"""
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA table_info(events)")
            columns = [col[1] for col in cursor.fetchall()]

            if 'reminder_offset' not in columns:
                self.conn.execute("ALTER TABLE events ADD COLUMN reminder_offset INTEGER DEFAULT 0")
                logger.info("Добавлен столбец reminder_offset в таблицу events")

    def _migrate_v4(self):
        """Миграция на версию 4: добавление таблиц partners, lists, list_items, notifications"""
        with self.conn:
            cursor = self.conn.cursor()

            def table_exists(name):
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
                return cursor.fetchone() is not None

            if not table_exists("partners"):
                self.conn.execute("""
                CREATE TABLE partners (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requester_id INTEGER NOT NULL,
                    partner_id INTEGER NOT NULL,
                    confirmed BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                logger.info("Создана таблица partners")

            if not table_exists("lists"):
                self.conn.execute("""
                CREATE TABLE lists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner_id INTEGER NOT NULL,
                    partner_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                logger.info("Создана таблица lists")

            if not table_exists("list_items"):
                self.conn.execute("""
                CREATE TABLE list_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    list_id INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    image_path TEXT,
                    due_date TEXT,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                logger.info("Создана таблица list_items")

            if not table_exists("notifications"):
                self.conn.execute("""
                CREATE TABLE notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    read BOOLEAN DEFAULT 0
                )
                """)
                logger.info("Создана таблица notifications")


    # ========== User Methods ==========
    def user_exists(self, user_id: int) -> bool:
        """Проверка существования пользователя"""
        query = "SELECT 1 FROM users WHERE user_id = ? LIMIT 1"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, (user_id,))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"[user_exists] Ошибка при проверке существования пользователя {user_id}: {e}")
            return False

    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None,
                 language_code: str = None) -> bool:
        """Добавление/обновление пользователя"""
        query = """
        INSERT OR REPLACE INTO users 
        (user_id, username, first_name, last_name, language_code, last_active)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            user_id, username, first_name,
            last_name, language_code, datetime.now()
        )

        try:
            with self.conn:
                self.conn.execute(query, params)
            logger.info(f"Пользователь {user_id} добавлен/обновлен")
            return True
        except Exception as e:
            logger.error(f"[add_user] Ошибка при добавлении пользователя {user_id}: {e}")
            return False

    def set_subscription(self, user_id: int, status: bool) -> bool:
        """Установка статуса подписки для пользователя"""
        query = """
        UPDATE users 
        SET is_subscribed = ?, last_active = ?
        WHERE user_id = ?
        """
        try:
            with self.conn:
                self.conn.execute(query, (status, datetime.now(), user_id))
            logger.info(f"Пользователю {user_id} статус подписки изменен на: {status}")
            return True
        except Exception as e:
            logger.error(f"[set_subscription] Ошибка при установке статуса подписки пользователя {user_id}: {e}")
            return False

    def get_user_info(self, user_id: int) -> Optional[Tuple]:
        """Получение информации о пользователе"""
        query = """
        SELECT username, first_name, last_name, created_at, last_active, is_subscribed 
        FROM users 
        WHERE user_id = ?
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, (user_id,))
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"[get_user_info] Ошибка при получении информации о пользователе {user_id}: {e}")
            return None

    def is_user_subscribed(self, user_id: int) -> Optional[bool]:
        """Проверка статуса подписки пользователя"""
        query = "SELECT is_subscribed FROM users WHERE user_id = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"[is_user_subscribed] Ошибка при получении статуса подписки {user_id}: {e}")
            return None

    def get_subscribed_users(self) -> Set[int]:
        """Получение ID всех подписанных пользователей"""
        query = "SELECT user_id FROM users WHERE is_subscribed = TRUE"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"[get_subscribed_users] Ошибка при получении подписчиков: {e}")
            return set()


    def get_user_id_by_username(self, username: str) -> int | None:
        """Получение ID пользователя по его username"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(
                    "SELECT user_id FROM users WHERE username = ?", (username,)
                )
                if result := cursor.fetchone():
                    return result[0]
                return None
        except sqlite3.Error as e:
            logger.error(f"[get_user_id_by_username] Ошибка при получении ID по username: {e}")
            return None

    def get_username_by_user_id(self, user_id):
        """Получение username пользователя по его ID"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(
                    "SELECT username FROM users WHERE user_id = ?", (user_id,)
                )
                if result := cursor.fetchone():
                    return result[0]
                return None
        except sqlite3.Error as e:
            logger.error(f"[get_username_by_user_id] Ошибка при получении username по ID: {e}")
            return None

    # ========== Compliment Methods ==========
    def add_compliment(self, text: str) -> bool:
        """Добавление нового комплимента"""
        query = "INSERT INTO compliments (text) VALUES (?)"
        try:
            with self.conn:
                self.conn.execute(query, (text,))
            logger.info(f"Комплимент успешно добавлен: {text[:20]}...")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"[add_compliment] Комплимент уже существует: {text[:20]}...")
            return False
        except Exception as e:
            logger.error(f"[add_compliment] Ошибка при добавлении комплимента: {e}")
            return False

    def get_random_compliment(self, user_id: int) -> Optional[Tuple[int, str]]:
        def _fetch_available_compliment() -> Optional[Tuple[int, str]]:
            query = """
            SELECT id, text FROM compliments
            WHERE is_active = TRUE
              AND id NOT IN (
                SELECT compliment_id FROM sent_compliments WHERE user_id = ?
            )
            ORDER BY RANDOM()
            LIMIT 1
            """
            try:
                cursor = self.conn.cursor()
                cursor.execute(query, (user_id,))
                return cursor.fetchone()
            except sqlite3.Error as e:
                logger.error(f"[_fetch_available_compliment] Ошибка при выполнении запроса: {e}")

        try:
            compliment = _fetch_available_compliment()

            if compliment:
                return compliment

            logger.info(f"Все комплименты пользователю {user_id} отправлены. Очистка истории.")
            self.reset_user_compliments(user_id)

            return _fetch_available_compliment()

        except Exception as e:
            logger.error(f"[get_random_compliment] Ошибка при получении случайного комплимента для: {user_id}: {e}")
            return None

    def record_sent_compliment(self, user_id: int, compliment_id: int) -> bool:
        """Запись отправленного комплимента в отдельную таблицу"""
        query = """
        INSERT INTO sent_compliments (user_id, compliment_id)
        VALUES (?, ?)
        """
        try:
            with self.conn:
                self.conn.execute(query, (user_id, compliment_id))
            logger.info(f"Записан комплимент {compliment_id} для пользователя: {user_id}")
            return True
        except Exception as e:
            logger.error(f"[record_sent_compliment] Ошибка при отправке комплимента: {e}")
            return False

    def reset_user_compliments(self, user_id: int) -> None:
        """Сброс истории комплиментов для пользователя"""
        query = "DELETE FROM sent_compliments WHERE user_id = ?"
        try:
            with self.conn:
                self.conn.execute(query, (user_id,))
            logger.info(f"[reset_user_compliments] Успешно сброшена история комплиментов для пользователя {user_id}")
        except Exception as e:
            logger.error(f"[reset_user_compliments] Ошибка при сбросе комплиментов для пользователя {user_id}: {e}")

    # ========== Wishlist Methods ==========
    def add_wish(self, user_id: int, wish_text: str) -> bool:
        """Добавление желания в вишлист"""
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO wishlist (user_id, wish_text) VALUES (?, ?)",
                    (user_id, wish_text)
                )
            return True
        except Exception as e:
            logger.error(f"[add_wish] Ошибка при добавлении желания: {e}")
            return False

    def get_user_wishes(self, user_id: int) -> list:
        """Получение желаний текущего пользователя"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id, wish_text, is_fulfilled FROM wishlist WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"[get_user_wishes] Ошибка при получении своих желаний: {e}")
            return []

    def get_partner_wishes(self, user_id: int) -> list:
        """Получение желаний партнера"""
        from config import ADMIN_ID, MIUS_ID
        partner_id = MIUS_ID if user_id == ADMIN_ID else ADMIN_ID

        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT id, wish_text FROM wishlist 
                   WHERE user_id = ? AND is_fulfilled = FALSE
                   ORDER BY created_at DESC""",
                (partner_id,)
            )
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"[get_partner_wishes] Ошибка при получении желаний партнера: {e}")
            return []

    def mark_fulfilled(self, wish_id: int) -> bool:
        """Пометить желание как исполненное"""
        try:
            with self.conn:
                self.conn.execute(
                    "UPDATE wishlist SET is_fulfilled = TRUE, fulfilled_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (wish_id,)
                )
            return True
        except Exception as e:
            logger.error(f"[mark_fulfilled] Ошибка при отметке желания исполненным: {e}")
            return False

    def delete_wish(self, wish_id: int, user_id: int) -> bool:
        """Удаление желания с проверкой владельца"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM wishlist WHERE id = ? AND user_id = ?",
                    (wish_id, user_id))
                if not cursor.fetchone():
                    return False

                cursor.execute(
                    "DELETE FROM wishlist WHERE id = ?",
                    (wish_id,))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"[delete_wish] Ошибка при удалении желания {wish_id}: {e}")
            return False

    # ========== Stats Methods ==========
    def get_stats(self) -> Dict:
        """Основная статистика бота для пользователей"""
        try:
            with self.conn:
                cursor = self.conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM users")
                total_users = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM users WHERE is_subscribed = TRUE")
                subscribed_users = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM compliments WHERE is_active = TRUE")
                total_compliments = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT COUNT(*) FROM sent_compliments 
                    WHERE DATE(sent_at) = DATE('now')
                """)
                sent_today = cursor.fetchone()[0]

            return {
                'total_users': total_users,
                'subscribed_users': subscribed_users,
                'total_compliments': total_compliments,
                'sent_today': sent_today
            }
        except Exception as e:
            logging.error(f"Failed to get stats: {e}")
            return {
                'total_users': 0,
                'subscribed_users': 0,
                'total_compliments': 0,
                'sent_today': 0
            }

    def get_compliments_count(self) -> int:
        """Количество активных комплиментов"""
        query = "SELECT COUNT(*) FROM compliments WHERE is_active = TRUE"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"[get_compliments_count] Ошибка при получении общего количества комплиментов: {e}")
            return 0

    def get_sent_today_count(self) -> int:
        """Количество отправленных в текущий день комплиментов"""
        query = """
        SELECT COUNT(*) FROM sent_compliments 
        WHERE DATE(sent_at) = DATE('now')
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"[get_sent_today_count] Ошибка при получении количества отправленных комплиментов сегодня: {e}")
            return 0

    def get_last_compliment_time(self) -> Optional[str]:
        """Получение времения последней отправки комплимента"""
        query = "SELECT MAX(sent_at) FROM sent_compliments"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            result = cursor.fetchone()[0]

            if isinstance(result, str):
                try:
                    result = datetime.strptime(result, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    return result

            if hasattr(result, 'strftime'):
                return result.strftime('%Y-%m-%d %H:%M:%S')
            return str(result) if result else None

        except Exception as e:
            logger.error(f"[get_last_compliment_time] Ошибка при получении времени последнего отправленного комплимента: {e}")
            return None

    # ========== Backup Methods ==========
    def backup_database(self, backup_path: str = None) -> Optional[str]:
        """Создание резервной копии базы данных"""
        if not backup_path:
            backup_path = f"data/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

        try:
            with sqlite3.connect(backup_path) as backup:
                self.conn.backup(backup)
            logger.info(f"Бэкап БД успешно создан {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"[backup_database] Ошибка при создании бэкапа БД: {e}")
            return None

    def __del__(self):
        """Закрытие соединения при удалении объекта"""
        if hasattr(self, 'conn'):
            self.conn.close()
            logger.info("Соединение с БД успешно закрыто")

    def get_subscribed_users_count(self) -> int:
        """Количество подписанных пользователей"""
        query = "SELECT COUNT(*) FROM users WHERE is_subscribed = TRUE"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"[get_subscribed_users_count] Ошибка при получении количества подписчиков: {e}")
            return 0

    def get_detailed_stats(self) -> Dict:
        """Подробная статистика для админа с обработкой разных форматов времени"""
        try:
            with self.conn:
                cursor = self.conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM users")
                total_users = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM users WHERE is_subscribed = TRUE")
                active_subs = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT COUNT(*) FROM users 
                    WHERE datetime(created_at) >= datetime('now', '-24 hours')
                """)
                new_users = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM compliments")
                total_comps = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM compliments WHERE is_active = TRUE")
                active_comps = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT COUNT(*) FROM sent_compliments 
                    WHERE DATE(sent_at) = DATE('now')
                """)
                sent_today = cursor.fetchone()[0]

                cursor.execute("SELECT MAX(sent_at) FROM sent_compliments")
                last_sent = cursor.fetchone()[0]

                last_sent_str = None
                if last_sent:
                    if isinstance(last_sent, str):
                        last_sent_str = last_sent
                    elif hasattr(last_sent, 'strftime'):
                        last_sent_str = last_sent.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        last_sent_str = str(last_sent)

            return {
                'total_users': total_users,
                'active_subscriptions': active_subs,
                'new_users_24h': new_users,
                'total_compliments': total_comps,
                'active_compliments': active_comps,
                'sent_today': sent_today,
                'last_sent_time': last_sent_str
            }
        except Exception as e:
            logger.error(f"[get_detailed_stats] Ошибка при получении детализированной статистики: {e}")
            return {
                'total_users': 0,
                'active_subscriptions': 0,
                'new_users_24h': 0,
                'total_compliments': 0,
                'active_compliments': 0,
                'sent_today': 0,
                'last_sent_time': None
            }

    # ========== Reminders Methods ==========
    def save_event(self, user_id: int, year: int, month: int, day: int,
                   time: str, event_description: str, all_day: int = 0,
                   repeat: int = 0, reminder_offset: int = 0) -> Optional[int]:
        """Сохранение напоминания пользователя"""
        if self.conn is None:
            self.conn()
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO events 
                (user_id, year, month, day, time, event_description, all_day, repeat, reminder_offset)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, year, month, day, time, event_description, all_day, repeat, reminder_offset))
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"[save_event] Ошибка при сохранении напоминания в БД: {e}")
            return None

    def get_all_events(self, user_id: Optional[int] = None,
                       only_future: bool = False) -> List[Dict]:
        """Получение всех напоминаний пользователя"""
        query = """
            SELECT id, user_id, year, month, day, time, 
                   event_description, all_day, repeat, reminder_offset
            FROM events
            """
        params = []

        conditions = []
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)

        if only_future:
            conditions.append("""
                (datetime(year || '-' || month || '-' || day || ' ' || time) > datetime('now')
                OR repeat = 1
                """)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            return [{
                'id': row[0],
                'user_id': row[1],
                'year': row[2],
                'month': row[3],
                'day': row[4],
                'time': row[5],
                'event_description': row[6],
                'all_day': bool(row[7]),
                'repeat': bool(row[8]),
                'reminder_offset': row[9]
            } for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[get_all_events] Ошибка при получении напоминаний: {e}") or []
            return []

    def delete_event(self, event_id, user_id=None):
        """Удаление напоминания пользователя"""
        try:
            with self.conn:
                cursor = self.conn.cursor()

                query = "DELETE FROM events WHERE id = ?"
                params = [event_id]

                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)

                cursor.execute(query, params)
                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"[delete_event] Ошибка при удалении напоминания из БД: {e}")
            return False

    def update_event(self, event_id: int, year: int, month: int, day: int,
                     time: str, event_description: str, all_day: int = 0,
                     repeat: int = 0) -> bool:
        """Обновление напоминания пользователя"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute('''
                    UPDATE events
                    SET year = ?, month = ?, day = ?, time = ?, 
                        event_description = ?, all_day = ?, repeat = ?
                    WHERE id = ?
                ''', (year, month, day, time, event_description, all_day, repeat, event_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"[update_event] Ошибка при обновлении напоминания у пользователя: {event_id}: {e}")
            return False

    def get_event_datetime(self, event_id: int) -> Optional[datetime]:
        """Получение даты напоминания"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT year, month, day, time FROM events WHERE id = ?
            ''', (event_id,))
            row = cursor.fetchone()
            if row:
                hour, minute = map(int, row[3].split(':'))
                return datetime(
                    year=int(row[0]),
                    month=int(row[1]),
                    day=int(row[2]),
                    hour=hour,
                    minute=minute
                )
            return None
        except Exception as e:
            logger.error(f"[get_event_datetime] Ошибка при получении datetime для пользователя: {event_id}: {e}")
            return None

    def cleanup_old_events(self, days: int = 30) -> int:
        """Очистка старых напоминаний"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute('''
                    DELETE FROM events 
                    WHERE datetime(year || '-' || month || '-' || day || ' ' || time) < datetime('now', ?)
                    AND repeat = 0
                ''', (f'-{days} days',))
                return cursor.rowcount
        except Exception as e:
            logger.error(f"[cleanup_old_events] Ошибка при очистке старых событий: {e}")
            return 0

    def update_event_description(self, event_id, new_text, user_id=None):
        """Обновление описания напоминания"""
        try:
            query = "UPDATE events SET event_description = ? WHERE id = ?"
            params = [new_text, event_id]

            if user_id is not None:
                query += " AND user_id = ?"
                params.append(user_id)

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                return cursor.rowcount > 0

            if cursor.rowcount > 0:
                logger.info(f"Event {event_id} updated successfully.")
            else:
                logger.warning(f"No event updated. Possibly wrong event_id or user_id.")
        except Exception as e:
            logger.error(f"Error updating event description: {e}")
            return False

    def update_event_date(self, event_id, new_day, new_month, new_year=None, user_id=None):
        """Обновление даты события"""
        try:
            query = "UPDATE events SET day = ?, month = ?"
            params = [new_day, new_month]

            if new_year is not None:
                query += ", year = ?"
                params.append(new_year)

            query += " WHERE id = ?"
            params.append(event_id)

            if user_id is not None:
                query += " AND user_id = ?"
                params.append(int(user_id))

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"[update_event_date] Ошибка при обновлении даты напоминания: {e}")
            return False

    def update_event_time(self, event_id, new_time, user_id=None):
        """Обновление времени события"""
        try:
            query = "UPDATE events SET time = ? WHERE id = ?"
            params = [new_time, event_id]

            if user_id is not None:
                query += " AND user_id = ?"
                params.append(int(user_id))

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"[update_event_date] Ошибка при обновлении времени напоминания: {e}")
            return False

    def update_event_repeat(self, event_id, repeat_value, user_id=None):
        """Обновление повторения события"""
        try:
            query = "UPDATE events SET repeat = ? WHERE id = ?"
            params = [repeat_value, event_id]

            if user_id is not None:
                query += " AND user_id = ?"
                params.append(int(user_id))

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"[update_event_repeat] Ошибка при обновлении повторения напоминания: {e}")
            return False

    # ========== Partner Methods ==========
    def send_partner_request(self, requester_id: int, partner_id: int) -> bool:
        """Отправка запроса на партнерство"""
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO partners (requester_id, partner_id, confirmed)
                    VALUES (?, ?, 0)
                    """,
                    (requester_id, partner_id)
                )
                return True
        except sqlite3.Error as e:
            logger.error(f"[send_partner_request] Ошибка при отправке запроса партнеру: {e}")
            return False

    def confirm_partner_request(self, requester_id: int, partner_id: int) -> bool:
        """Подтверждение запроса на партнерство"""
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    UPDATE partners
                    SET confirmed = 1
                    WHERE requester_id = ? AND partner_id = ?
                    """,
                    (requester_id, partner_id)
                )
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"[confirm_partner] Ошибка при подтвержждении партнера в БД: {e}")
            return False

    def get_partner(self, user_id: int) -> Optional[int]:
        """Получение партнера из БД"""
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    SELECT requester_id FROM partners WHERE partner_id = ? AND confirmed = 1
                    UNION
                    SELECT partner_id FROM partners WHERE requester_id = ? AND confirmed = 1
                    """,
                    (user_id, user_id)
                )
                if result := cursor.fetchone():
                    return result[0]
                return None
        except sqlite3.Error as e:
            logger.error(f"[get_partner] Ошибка при получении партнера из БД: {e}")
            return None

    def delete_partner(self, user_id):
        """Удаление партнера из БД"""
        try:
            with self.conn:
                cursor = self.conn.execute(
                    "SELECT requester_id, partner_id FROM partners WHERE requester_id = ? OR partner_id = ?",
                    (user_id, user_id)
                )
                if row := cursor.fetchone():
                    requester_id, partner_id = row
                    self.conn.execute(
                        "DELETE FROM partners WHERE requester_id = ? OR partner_id = ?",
                        (user_id, user_id)
                    )
                    other_id = partner_id if requester_id == user_id else requester_id
                    return True, other_id
                return False, None
        except sqlite3.Error as e:
            logging.error(f"[delete_partner] Ошибка при удалении партнера из БД: {e}")
            return False, None

    def has_pending_request(self, requester_id: int, partner_id: int) -> bool:
        """Проверка заявки на партнерство"""
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    SELECT 1 FROM partners
                    WHERE requester_id = ? AND partner_id = ? AND confirmed = 0
                    """,
                    (requester_id, partner_id)
                )
                return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"[has_pending_request] Ошибка при проверке заявки на партнерство: {e}")
            return False

    def get_last_request_time(self, requester_id: int, partner_id: int) -> str:
        """Получение времени последнего запроса между двумя пользователями"""
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    SELECT created_at FROM partners
                    WHERE requester_id = ? AND partner_id = ? AND confirmed = 0
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (requester_id, partner_id)
                )
                row = cursor.fetchone()
                if row:
                    return row[0]  # Время последнего запроса
                return None
        except sqlite3.Error as e:
            logger.error(f"[get_last_request_time] Ошибка при получении времени последнего запроса: {e}")
            return None

    # ========== List Methods ==========
    def create_list(self, name: str, owner_id: int, partner_id: int) -> Optional[int]: #
        """Создание списка пользователя"""
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO lists (name, owner_id, partner_id)
                    VALUES (?, ?, ?)
                    """,
                    (name, owner_id, partner_id)
                )
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"[create_list] Ошибка при создании списка в БД: {e}")
            return None

    def add_list_item(self, list_id: int, description: str, created_by: int,
            image_path: Optional[str] = None,
            due_date: Optional[str] = None) -> bool:
        """Добавление элементов в список пользователя"""
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO list_items (list_id, description, image_path, due_date, created_by)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (list_id, description, image_path, due_date, created_by)
                )
                return True
        except sqlite3.Error as e:
            logger.error(f"[add_list_item] Ошибка при добавлении элемента списка в БД: {e}")
            return False

    def get_user_lists(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение списков пользователя"""
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    SELECT * FROM lists
                    WHERE owner_id = ? OR partner_id = ?
                    """,
                    (user_id, user_id)
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"[get_lists_by_user] Ошибка при получении списков из БД: {e}")
            return []

    def get_list_items(self, list_id: int) -> List[Dict[str, Any]]:
        """Получение элементов списка пользователя"""
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    SELECT * FROM list_items
                    WHERE list_id = ?
                    ORDER BY created_at ASC
                    """,
                    (list_id,)
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"[get_list_items] Ошибка при получении элементов списка из БД: {e}")
            return []

    def delete_list(self, list_id):
        """Удаление списка пользователя"""
        try:
            with self.conn:
                self.conn.execute("DELETE FROM list_items WHERE list_id = ?", (list_id,))
                self.conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))
                return True
        except sqlite3.Error as e:
            logger.error(f"[delete_list] Ошибка при удалении списка из БД: {e}")
            return False

    def delete_list_item(self, item_id: int) -> bool:
        """Удаление элемента списка пользователя"""
        try:
            with self.conn:
                self.conn.execute("DELETE FROM list_items WHERE id = ?", (item_id,))
                return True
        except sqlite3.Error as e:
            logger.error(f"[delete_list_item] Ошибка при удалении элемента списка: {e}")
            return False

    def update_listitem_description(self, item_id, new_text, list_id=None):
        """Обновление названия элемента списка пользователя"""
        try:
            query = "UPDATE list_items SET description = ?"
            params = [new_text]

            query += " WHERE id = ?"
            params.append(item_id)

            if list_id is not None:
                query += " AND list_id = ?"
                params.append(int(list_id))

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"[update_listitem_description] Ошибка при обновлении описания элемента списка: {e}")
            return False

    def update_item_date(self, new_date, item_id, list_id=None):  # Обновление даты события
        """Обновление даты элемента списка пользователя"""
        try:
            query = "UPDATE list_items SET due_date = ?"
            params = [new_date]

            query += " WHERE id = ?"
            params.append(item_id)

            if list_id is not None:
                query += " AND list_id = ?"
                params.append(int(list_id))

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"[update_item_date] Ошибка при обновлении даты элемента списка: {e}")
            return False

    def update_item_photo(self, item_id, new_image_path, list_id=None):
        """Обновление пути к фото для элемента списка пользователя"""
        try:
            query = "UPDATE list_items SET image_path = ?"
            params = [new_image_path]

            query += " WHERE id = ?"
            params.append(item_id)

            if list_id is not None:
                query += " AND list_id = ?"
                params.append(int(list_id))

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"[update_item_photo] Ошибка при обновлении фото элемента списка: {e}")
            return False

    def get_listtitle_by_id(self, list_id):
        """Получение названия списка пользователя по его ID"""
        try:
            query = "SELECT name FROM lists WHERE id = ?"
            params = [list_id]

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                result = cursor.fetchone()
                if result:
                    return result[0]  # Название списка
                else:
                    return None  # Если список не найден
        except sqlite3.Error as e:
            logger.error(f"[get_listtitle_by_id] Ошибка при получении названия листа из БД: {e}")
            return None

    def get_listID_by_itemid(self, item_id):
        """Получение ID списка пользователя по ID его элемента"""
        try:
            query = "SELECT list_id FROM list_items WHERE id = ?"
            params = [item_id]

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                result = cursor.fetchone()
                if result:
                    return result[0]  # Название списка
                else:
                    return None  # Если список не найден
        except sqlite3.Error as e:
            logger.error(f"[get_listtitle_by_id] Ошибка при получении названия листа из БД: {e}")
            return None

    def get_itemname_by_id(self, item_id):
        """Получение названия элемента списка пользователя по его ID"""
        try:
            query = "SELECT description FROM list_items WHERE id = ?"
            params = [item_id]

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                result = cursor.fetchone()
                if result:
                    return result[0]  # Название списка
                else:
                    return None  # Если список не найден
        except sqlite3.Error as e:
            logger.error(f"[get_itemname_by_id] Ошибка при получении названия элемента списка из БД: {e}")
            return None