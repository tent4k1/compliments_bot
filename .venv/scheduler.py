import logging
from datetime import datetime, time as dt_time
from threading import Thread
from typing import Dict, Optional, Tuple
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from database import Database


class ComplimentScheduler:
    def __init__(self, bot, db):
        """
        Инициализация планировщика комплиментов.
        """
        self.bot = bot
        self.db = db
        self.scheduler = BackgroundScheduler()
        self._running = False
        self.logger = logging.getLogger(__name__)

        # Инициализация стандартных комплиментов
        self._initialize_default_compliments()

    def _initialize_default_compliments(self) -> None:
        """Инициализация стандартных комплиментов при первом запуске"""
        try:
            if not self.db.get_compliments_count():
                default_compliments = [
                    "Вау, твоя улыбка ослепительна!",
                    "Твоя улыбка делает мир лучше!",
                    "Ты сегодня особенно прекрасен(на)!",
                    "Твоя энергия заряжает всех вокруг!"
                ]

                for comp in default_compliments:
                    self.db.add_compliment(comp)

                self.logger.info("Initialized default compliments in DB")
        except Exception as e:
            self.logger.error(f"Failed to initialize default compliments: {e}")
            raise

    def send_compliment_to_user(self, user_id: int) -> bool:
        """
        Отправка комплимента конкретному пользователю.

        Args:
            user_id: ID пользователя

        Returns:
            bool: Успешность отправки
        """
        try:
            compliment = self.db.get_random_compliment()
            if not compliment:
                self.logger.warning(f"No compliments available for user {user_id}")
                return False

            compliment_id, text = compliment
            self.bot.send_message(user_id, f"💖 Комплимент дня:\n\n{text}")
            self.db.record_sent_compliment(user_id, compliment_id)
            self.logger.info(f"Sent compliment to user {user_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send to user {user_id}: {e}")
            if "bot was blocked" in str(e).lower():
                self.db.set_subscription(user_id, False)
                self.logger.info(f"Unsubscribed blocked user {user_id}")
            return False

    def send_compliments(self) -> Tuple[int, int]:
        """
        Отправка комплиментов всем подписанным пользователям.

        Returns:
            Tuple[int, int]: (количество успешных отправок, общее количество пользователей)
        """
        try:
            users = self.db.get_subscribed_users()
            if not users:
                return (0, 0)

            compliment = self.db.get_random_compliment()
            if not compliment:
                return (0, len(users))

            compliment_id, text = compliment
            success = 0

            for user_id in users:
                try:
                    self.bot.send_message(user_id, f"✨ {text}")
                    self.db.record_sent_compliment(user_id, compliment_id)
                    success += 1
                except Exception as e:
                    self.logger.error(f"Failed to send to user {user_id}: {e}")
                    if "bot was blocked" in str(e).lower():
                        self.db.set_subscription(user_id, False)

            return (success, len(users))
        except Exception as e:
            self.logger.error(f"Error in send_compliments: {e}")
            return (0, 0)

    def schedule_daily_jobs(self) -> None:
        """Настройка ежедневного расписания отправки"""
        try:
            self.scheduler.remove_all_jobs()

            # Утренняя отправка (8:00)
            self.scheduler.add_job(
                self.send_compliments,
                trigger=CronTrigger(hour=8, minute=0),
                id='morning_compliment'
            )

            # Дневная отправка (14:30)
            self.scheduler.add_job(
                self.send_compliments,
                trigger=CronTrigger(hour=14, minute=30),
                id='afternoon_compliment'
            )

            # Вечерняя отправка (20:00)
            self.scheduler.add_job(
                self.send_compliments,
                trigger=CronTrigger(hour=20, minute=0),
                id='evening_compliment'
            )

            self.logger.info("Scheduled daily compliment jobs")
        except Exception as e:
            self.logger.error(f"Failed to schedule jobs: {e}")
            raise

    def start(self) -> None:
        """Запуск планировщика"""
        if self._running:
            self.logger.warning("Scheduler already running")
            return

        try:
            self.schedule_daily_jobs()
            self.scheduler.start()
            self._running = True
            self.logger.info("Compliment scheduler started")
        except Exception as e:
            self.logger.error(f"Failed to start scheduler: {e}")
            raise

    def stop(self) -> None:
        """Остановка планировщика"""
        if not self._running:
            self.logger.warning("Scheduler not running")
            return

        try:
            self.scheduler.shutdown()
            self._running = False
            self.logger.info("Compliment scheduler stopped")
        except Exception as e:
            self.logger.error(f"Failed to stop scheduler: {e}")
            raise

    def get_status(self) -> Dict:
        """
        Получение текущего статуса планировщика.
        """
        return {
            'status': 'running' if self._running else 'stopped',
            'subscribed_users': self.db.get_subscribed_users_count(),
            'active_compliments': self.db.get_compliments_count(),
            'last_sent': self.db.get_last_compliment_time(),
            'next_run': self._get_next_run_times()
        }

    def _get_next_run_times(self) -> Optional[Dict]:
        """Получение времени следующей отправки для каждого задания"""
        if not self._running:
            return None

        try:
            jobs = self.scheduler.get_jobs()
            return {job.id: str(job.next_run_time) for job in jobs}
        except Exception as e:
            self.logger.error(f"Failed to get next run times: {e}")
            return None

    def check_working(self):
        """Проверка состояния планировщика"""
        return {
            'status': 'running' if self._running else 'stopped',
            'users_count': self.db.get_subscribed_users_count(), 
            'compliments_available': self.db.get_compliments_count(),
            'last_compliment_sent': self.db.get_last_compliment_time(),
            'next_check': datetime.now().strftime('%H:%M:%S')
        }
