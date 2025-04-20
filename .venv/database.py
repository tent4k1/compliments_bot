import sqlite3
import threading
from pathlib import Path
from datetime import datetime
import logging
from typing import Optional, Tuple, List, Dict, Set

from pydantic.v1.utils import sequence_like

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('database.log'),
        logging.StreamHandler()
    ]
)
logging.basicConfig(level=logging.DEBUG)

# Включаем логирование для бота
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

class Database:
    _instance = None
    _lock = threading.Lock()
    DB_VERSION = 2  # Версия схемы базы данных

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

        # Подключение с настройками для надежности
        self.conn = sqlite3.connect(
            str(self.db_path),
            timeout=20,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False
        )
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

        # Проверяем и создаем таблицы
        self._create_tables()
        # Проверяем и выполняем миграции
        self._check_migrations()

        logging.info(f"Database initialized at {self.db_path}")

    def _ensure_data_dir(self):
        """Создание папки data если не существует"""
        try:
            Path('data').mkdir(exist_ok=True)
        except Exception as e:
            logging.error(f"Failed to create data directory: {e}")
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
                repeat INTEGER DEFAULT 0
            )
            """
        ]

        try:
            with self.conn:
                for table in tables:
                    self.conn.execute(table)
                # Устанавливаем текущую версию БД
                self.conn.execute("INSERT OR IGNORE INTO db_meta (version) VALUES (?)", (self.DB_VERSION,))
            logging.info("Database tables created/verified")
        except Exception as e:
            logging.error(f"Failed to create tables: {e}")
            raise

    def _check_migrations(self):
        """Проверка и выполнение необходимых миграций"""
        try:
            # Получаем текущую версию БД
            cursor = self.conn.cursor()
            cursor.execute("SELECT version FROM db_meta LIMIT 1")
            result = cursor.fetchone()
            current_version = result[0] if result else 0

            # Выполняем миграции последовательно
            for version in range(current_version + 1, self.DB_VERSION + 1):
                migration_method = getattr(self, f"_migrate_v{version}", None)
                if migration_method:
                    migration_method()
                    # Обновляем версию в БД
                    with self.conn:
                        self.conn.execute("UPDATE db_meta SET version = ?", (version,))
                    logging.info(f"Database migrated to version {version}")

        except Exception as e:
            logging.error(f"Migration failed: {e}")
            raise

    def _migrate_v1(self):
        """Миграция на версию 1: добавление language_code и last_active"""
        with self.conn:
            # Проверяем существование колонок перед добавлением
            cursor = self.conn.cursor()

            # Для language_code
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]

            if 'language_code' not in columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN language_code TEXT DEFAULT NULL")
                logging.info("Added language_code column to users table")

            if 'last_active' not in columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                logging.info("Added last_active column to users table")

    def _migrate_v2(self):
        """Миграция на версию 2: добавление таблицы db_meta"""
        with self.conn:
            # Проверяем существование таблицы db_meta
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_meta'")
            if not cursor.fetchone():
                self.conn.execute("""
                CREATE TABLE db_meta (
                    version INTEGER PRIMARY KEY
                )
                """)
                self.conn.execute("INSERT INTO db_meta (version) VALUES (2)")
                logging.info("Added db_meta table")

    # ========== User Methods ==========
    def user_exists(self, user_id: int) -> bool:
        """Проверка существования пользователя"""
        query = "SELECT 1 FROM users WHERE user_id = ? LIMIT 1"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, (user_id,))
            return cursor.fetchone() is not None
        except Exception as e:
            logging.error(f"Failed to check user existence {user_id}: {e}")
            return False

    def add_user(self, user_id: int, username: str = None,
                 first_name: str = None, last_name: str = None,
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
            logging.info(f"User {user_id} added/updated")
            return True
        except Exception as e:
            logging.error(f"Failed to add user {user_id}: {e}")
            return False

    def set_subscription(self, user_id: int, status: bool) -> bool:
        """Установка статуса подписки"""
        query = """
        UPDATE users 
        SET is_subscribed = ?, last_active = ?
        WHERE user_id = ?
        """
        try:
            with self.conn:
                self.conn.execute(query, (status, datetime.now(), user_id))
            logging.info(f"User {user_id} subscription set to {status}")
            return True
        except Exception as e:
            logging.error(f"Failed to set subscription for {user_id}: {e}")
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
            logging.error(f"Failed to get user info {user_id}: {e}")
            return None

    def is_user_subscribed(self, user_id: int) -> Optional[bool]:
        """Проверка статуса подписки"""
        query = "SELECT is_subscribed FROM users WHERE user_id = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logging.error(f"Failed to check subscription for {user_id}: {e}")
            return None

    def get_subscribed_users(self) -> Set[int]:
        """Получение ID всех подписанных пользователей"""
        query = "SELECT user_id FROM users WHERE is_subscribed = TRUE"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logging.error(f"Failed to get subscribed users: {e}")
            return set()

    # ========== Compliment Methods ==========
    def add_compliment(self, text: str) -> bool:
        """Добавление нового комплимента"""
        query = "INSERT INTO compliments (text) VALUES (?)"
        try:
            with self.conn:
                self.conn.execute(query, (text,))
            logging.info(f"Compliment added: {text[:20]}...")
            return True
        except sqlite3.IntegrityError:
            logging.warning(f"Compliment already exists: {text[:20]}...")
            return False
        except Exception as e:
            logging.error(f"Failed to add compliment: {e}")
            return False

    def get_random_compliment(self) -> Optional[Tuple[int, str]]:
        """Получение случайного активного комплимента"""
        query = """
        SELECT id, text FROM compliments 
        WHERE is_active = TRUE
        ORDER BY RANDOM() 
        LIMIT 1
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            return cursor.fetchone()
        except Exception as e:
            logging.error(f"Failed to get random compliment: {e}")
            return None

    def record_sent_compliment(self, user_id: int, compliment_id: int) -> bool:
        """Запись отправленного комплимента"""
        query = """
        INSERT INTO sent_compliments (user_id, compliment_id)
        VALUES (?, ?)
        """
        try:
            with self.conn:
                self.conn.execute(query, (user_id, compliment_id))
            logging.info(f"Recorded compliment {compliment_id} for user {user_id}")
            return True
        except Exception as e:
            logging.error(f"Failed to record sent compliment: {e}")
            return False

    # ========== Wishlist Methods ==========
    def add_wish(self, user_id: int, wish_text: str) -> bool:
        """Добавление желания в список"""
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO wishlist (user_id, wish_text) VALUES (?, ?)",
                    (user_id, wish_text)
                )
            return True
        except Exception as e:
            logging.error(f"Failed to add wish: {e}")
            return False

    def get_user_wishes(self, user_id: int) -> list:
        """Получение желаний пользователя"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id, wish_text, is_fulfilled FROM wishlist WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to get wishes: {e}")
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
            logging.error(f"Failed to get partner wishes: {e}")
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
            logging.error(f"Failed to mark wish fulfilled: {e}")
            return False

    def delete_wish(self, wish_id: int, user_id: int) -> bool:
        """Удаление желания с проверкой владельца"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                # Проверяем, что желание принадлежит пользователю
                cursor.execute(
                    "SELECT 1 FROM wishlist WHERE id = ? AND user_id = ?",
                    (wish_id, user_id))
                if not cursor.fetchone():
                    return False

                # Удаление желания
                cursor.execute(
                    "DELETE FROM wishlist WHERE id = ?",
                    (wish_id,))
                return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Failed to delete wish {wish_id}: {e}")
            return False

    # ========== Stats Methods ==========
    def get_stats(self) -> Dict:
        """Основная статистика бота"""
        try:
            with self.conn:
                cursor = self.conn.cursor()

                # Получаем общее количество пользователей
                cursor.execute("SELECT COUNT(*) FROM users")
                total_users = cursor.fetchone()[0]

                # Получаем количество подписанных пользователей
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_subscribed = TRUE")
                subscribed_users = cursor.fetchone()[0]

                # Получаем количество комплиментов
                cursor.execute("SELECT COUNT(*) FROM compliments WHERE is_active = TRUE")
                total_compliments = cursor.fetchone()[0]

                # Получаем количество отправленных сегодня комплиментов
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

    def get_detailed_stats(self) -> Dict:
        """Подробная статистика для админа"""
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

            cursor.execute("""
            SELECT MAX(sent_at) FROM sent_compliments
            """)
            last_sent = cursor.fetchone()[0]

        return {
            'total_users': total_users,
            'active_subscriptions': active_subs,
            'new_users_24h': new_users,
            'total_compliments': total_comps,
            'active_compliments': active_comps,
            'sent_today': sent_today,
            'last_sent_time': last_sent.strftime('%Y-%m-%d %H:%M:%S') if last_sent else None
        }

    def get_compliments_count(self) -> int:
        """Количество активных комплиментов"""
        query = "SELECT COUNT(*) FROM compliments WHERE is_active = TRUE"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            return cursor.fetchone()[0]
        except Exception as e:
            logging.error(f"Failed to get compliments count: {e}")
            return 0

    def get_sent_today_count(self) -> int:
        """Количество отправленных сегодня комплиментов"""
        query = """
        SELECT COUNT(*) FROM sent_compliments 
        WHERE DATE(sent_at) = DATE('now')
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            return cursor.fetchone()[0]
        except Exception as e:
            logging.error(f"Failed to get sent today count: {e}")
            return 0

    def get_last_compliment_time(self) -> Optional[str]:
        """Время последней отправки комплимента"""
        query = "SELECT MAX(sent_at) FROM sent_compliments"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            result = cursor.fetchone()[0]

            # Если результат - строка, преобразуем в datetime
            if isinstance(result, str):
                try:
                    result = datetime.strptime(result, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    return result  # Возвращаем как есть, если не удалось распарсить

            # Если результат - datetime, форматируем
            if hasattr(result, 'strftime'):
                return result.strftime('%Y-%m-%d %H:%M:%S')
            return str(result) if result else None

        except Exception as e:
            logging.error(f"Failed to get last compliment time: {e}")
            return None

    # ========== Backup Methods ==========
    def backup_database(self, backup_path: str = None) -> Optional[str]:
        """Создание резервной копии базы данных"""
        if not backup_path:
            backup_path = f"data/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

        try:
            with sqlite3.connect(backup_path) as backup:
                self.conn.backup(backup)
            logging.info(f"Database backup created at {backup_path}")
            return backup_path
        except Exception as e:
            logging.error(f"Failed to create backup: {e}")
            return None

    def __del__(self):
        """Закрытие соединения при удалении объекта"""
        if hasattr(self, 'conn'):
            self.conn.close()
            logging.info("Database connection closed")

    def get_subscribed_users_count(self) -> int:
        """Количество подписанных пользователей"""
        query = "SELECT COUNT(*) FROM users WHERE is_subscribed = TRUE"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            return cursor.fetchone()[0]
        except Exception as e:
            logging.error(f"Failed to get subscribed users count: {e}")
            return 0

    def get_detailed_stats(self) -> Dict:
        """Подробная статистика для админа с обработкой разных форматов времени"""
        try:
            with self.conn:
                cursor = self.conn.cursor()

                # Получаем базовую статистику
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

                # Получаем и обрабатываем время последней отправки
                cursor.execute("SELECT MAX(sent_at) FROM sent_compliments")
                last_sent = cursor.fetchone()[0]

                # Обработка разных форматов времени
                last_sent_str = None
                if last_sent:
                    if isinstance(last_sent, str):
                        # Если время пришло как строка - возвращаем как есть
                        last_sent_str = last_sent
                    elif hasattr(last_sent, 'strftime'):
                        # Если это datetime объект - форматируем
                        last_sent_str = last_sent.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        # Другие случаи - преобразуем в строку
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
            logging.error(f"Failed to get detailed stats: {e}")
            return {
                'total_users': 0,
                'active_subscriptions': 0,
                'new_users_24h': 0,
                'total_compliments': 0,
                'active_compliments': 0,
                'sent_today': 0,
                'last_sent_time': None
            }

    def save_event(self, user_id, year, month, day, time, event_description, all_day=0, repeat=0):
        if self.conn is None:
            self.conn()
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM events")
        count = cursor.fetchone()[0]
        print(f"Number of events in DB: {count}")
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                        INSERT INTO events (user_id, year, month, day, time, event_description, all_day, repeat)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, year, month, day, time, event_description, all_day, repeat))
            self.conn.commit()
            print("Event saved successfully!")
        except Exception as e:
            print(f"Error saving event: {e}")

    def get_all_events(self, *, user_id=None):
        cursor = self.conn.cursor()
        if user_id:
            cursor.execute("SELECT id, year, month, day, time, event_description FROM events WHERE user_id=?",
                           (user_id,))
        else:
            cursor.execute("SELECT id, year, month, day, time, event_description FROM events")
        return cursor.fetchall()

    def delete_event(self, id):
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM events WHERE id = ?", (id,))
            self.conn.commit()
            return cursor.rowcount > 0  # Возвращаем True, если событие было удалено
        except Exception as e:
            print(f"Ошибка при удалении события: {e}")
            return False

    def update_event(self, id, year, month, day, time, event_, all_day=0, repeat=0):
        if self.conn is None:
            self.conn()
        cursor = self.conn.cursor()
        cursor.execute('''UPDATE events
                          SET year = ?, month = ?, day = ?, time = ?, event_description = ?, all_day = ?, repeat = ?
                          WHERE id = ?''',
                       (year, month, day, time, event_description, all_day, repeat, id))
        self.conn.commit()

    def save_event(self, user_id, year, month, day, time, event_description, all_day, repeat):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO events (user_id, year, month, day, time, event_description, all_day, repeat)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, year, month, day, time, event_description, all_day, repeat))
            self.conn.commit()
        except Exception as e:
            print(f"Error during saving event: {e}")