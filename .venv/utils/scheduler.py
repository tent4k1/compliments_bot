import logging
import requests

from datetime import timedelta
from datetime import datetime, time as dt_time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from pytz import timezone
from threading import Thread
from typing import Dict, Optional, Tuple
from config import WEATHER, WEATHER, DEFAULT_CITY
from database import Database
from utils.weather_handlers import Weather_Handlers


class ComplimentScheduler:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.wh = Weather_Handlers()
        self.scheduler = BackgroundScheduler(timezone=timezone('Europe/Moscow'))
        self._running = False
        self.logger = logging.getLogger(__name__)
        self.logger.info("Инициализация планировщика...")

        try:
            if not self.scheduler.running:
                self.scheduler.start()
                self._running = True
                self.logger.info("Планировщик успешно запущен")
        except Exception as e:
            self.logger.critical(f"Ошибка при запуске планировщика: {e}")
            raise

        try:
            self._initialize_default_compliments()
            self._restore_event_reminders()
            self.schedule_daily_jobs()
            self._schedule_weather()
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации планироващиков: {e}")

    # ========== Compliments Methods ==========
    def _initialize_default_compliments(self) -> None: # Инициализация стандартных комплиментов при первом запуске
        try:
            if not self.db.get_compliments_count():
                default_compliments = [
                    "Вау, твоя улыбка ослепительна!",
                    "Твоя улыбка делает мир лучше!",
                    "Ты сегодня особенно прекрасна!",
                    "Твоя энергия заряжает всех вокруг!"
                ]

                for comp in default_compliments:
                    self.db.add_compliment(comp)

                self.logger.info("Стандартные комплименты успешно инициализированы")
        except Exception as e:
            self.logger.error(f"[_initialize_default_compliments] Ошибка при инициализации комплиментов: {e}")
            raise

    def send_compliment_to_user(self, user_id: int) -> bool: # Отправка комплимента конкретному пользователю
        try:
            compliment = self.db.get_random_compliment()
            if not compliment:
                self.logger.warning(f"[send_compliment_to_user] Нет доступных комплиментов для пользователя: {user_id}")
                return False

            compliment_id, text = compliment
            self.bot.send_message(user_id, f"💖 Комплимент дня:\n\n{text}")
            self.db.record_sent_compliment(user_id, compliment_id)
            self.logger.info(f"Отправлен комплимент пользователю: {user_id}")
            return True

        except Exception as e:
            self.logger.error(f"[send_compliment_to_user] Ошибка при отправке комплимента пользователю: {user_id}: {e}")
            if "bot was blocked" in str(e).lower():
                self.db.set_subscription(user_id, False)
                self.logger.info(f"Бот заблокирован у пользователя: {user_id}")
            return False

    def send_compliments(self) -> Tuple[int, int]: # Отправка комплиментов всем подписанным пользователям
        try:
            users = self.db.get_subscribed_users()
            if not users:
                return (0, 0)
        except Exception as e:
            self.logger.warning(f"[send_compliments] Ошибка при получении подписанных пользователей: {e}")

        try:
            compliment = self.db.get_random_compliment()
            if not compliment:
                return (0, len(users))
        except Exception as e:
            self.logger.warning(f"[send_compliments] Ошибка при получении случайного комплимента: {e}")

        try:
            compliment_id, text = compliment
            success = 0

            for user_id in users:
                try:
                    self.bot.send_message(user_id, f"✨ {text}")
                    self.db.record_sent_compliment(user_id, compliment_id)
                    success += 1
                except Exception as e:
                    self.logger.error(f"[send_compliments] Ошибка при отправке комплимента пользователю: {user_id}: {e}")
                    if "bot was blocked" in str(e).lower():
                        self.db.set_subscription(user_id, False)

            return (success, len(users))
        except Exception as e:
            self.logger.error(f"[send_compliments] Ошибка при отправке комплимента: {e}")
            return (0, 0)

    # ========== Jobs Methods ==========
    def schedule_daily_jobs(self) -> None: # Настройка ежедневного расписания отправки
        try:
            self.scheduler.remove_all_jobs()

            self.scheduler.add_job(
                self.send_compliments,
                trigger=CronTrigger(hour=8, minute=0),
                id='morning_compliment'
            )

            self.scheduler.add_job(
                self.send_compliments,
                trigger=CronTrigger(hour=14, minute=30),
                id='afternoon_compliment'
            )

            self.scheduler.add_job(
                self.send_compliments,
                trigger=CronTrigger(hour=20, minute=0),
                id='evening_compliment'
            )

            self.logger.info("Ежедневные комплименты успешно запущены")
        except Exception as e:
            self.logger.error(f"[schedule_daily_jobs] Ошибка при планировании ежедневных комплиментов: {e}")
            raise

    def start(self) -> None: # Запуск планировщика
        if self._running:
            self.logger.warning("Планировщик уже запущен")
            return

        try:
            self.schedule_daily_jobs()
            self.scheduler.start()
            self._running = True
            self.logger.info("Планировщик успешно запущен")
        except Exception as e:
            self.logger.error(f"[start] Ошибка при запуске планировщика: {e}")
            raise

    def stop(self) -> None: # Остановка планировщика
        if not self._running:
            self.logger.warning("[stop] Планировщик не запущен")
            return

        try:
            self.scheduler.shutdown()
            self._running = False
            self.logger.info("Планировщик успешно остановлен")
        except Exception as e:
            self.logger.error(f"[stop] Ошибка при остановке планировщика: {e}")
            raise

    def get_status(self) -> Dict: # Получение текущего статуса планировщика
        return {
            'status': 'running' if self._running else 'stopped',
            'subscribed_users': self.db.get_subscribed_users_count(),
            'active_compliments': self.db.get_compliments_count(),
            'last_sent': self.db.get_last_compliment_time(),
            'next_run': self._get_next_run_times()
        }

    def _get_next_run_times(self) -> Optional[Dict]: # Получение времени следующей отправки для каждого задания
        if not self._running:
            return None

        try:
            jobs = self.scheduler.get_jobs()
            return {job.id: str(job.next_run_time) for job in jobs}
        except Exception as e:
            self.logger.error(f"[_get_next_run_times] Ошибка при получении времени следующей отправки: {e}")
            return None

    def _get_daily_forecast(self, city_name: str) -> str: # Получение форматированного прогноза
        try:
            base_url = "http://api.openweathermap.org/data/2.5/forecast"
            params = {
                'q': city_name,
                'appid': WEATHER,
                'units': 'metric',
                'cnt': 12,  # 12 периодов по 2 часа
                'lang': 'ru'
            }

            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return "Город не найден"
            elif e.response.status_code == 401:
                return "Ошибка API ключа"
            else:
                return "Ошибка сервера"
        except Exception as e:
            self.logger.error(f"[_get_daily_forecast] Ошибка при получении погоды: {e}")

        try:
            forecast = []
            daytime_temps = []
            for item in data['list']:
                time_obj = datetime.fromtimestamp(item['dt'])
                time_str = time_obj.strftime('%H:%M')
                hour = time_obj.hour
                temp = item['main']['temp']

                weather_info = item['weather'][0] if item.get('weather') else {}
                weather_id = weather_info.get('id', 800)
                desc = weather_info.get('description')
                forecast.append(f"{self.wh.get_weather_icon(weather_id)} {time_str}: {temp}°C, {desc.capitalize()}")

                if 8 <= hour < 20:
                    daytime_temps.append(temp)

            if daytime_temps:
                avg_day_temp = sum(daytime_temps) / len(daytime_temps)
                temp_info = f"\n\n<b>Средняя дневная температура (08:00-20:00):</b> {avg_day_temp:.1f}°C"
            else:
                temp_info = "\n\n<b>Дневные данные недоступны</b>"

            return (
                    f"<b>🌤️ Прогноз погоды в {data['city']['name']} на сегодня:</b>\n\n" +
                    "\n".join(forecast) +
                    temp_info
            )
        except Exception as e:
            self.logger.error(f"[_get_daily_forecast] Ошибка при форматировани погоды: {e}")

    def check_working(self): # Проверка состояния планировщика
        return {
            'status': 'running' if self._running else 'stopped',
            'users_count': self.db.get_subscribed_users_count(),
            'compliments_available': self.db.get_compliments_count(),
            'last_compliment_sent': self.db.get_last_compliment_time(),
            'next_check': datetime.now().strftime('%H:%M:%S')
        }

    # ========== Weather's Jobs Methods ==========
    def _schedule_weather(self): # Настройка отправки в определенное время
        try:
            self.scheduler.add_job(
                self.send_daily_weather,
                trigger=CronTrigger(hour=20, minute=22),
                id='morning_weather'
            )
            self.logger.info("Weather forecast scheduled at 8:00 AM daily")
        except Exception as e:
            self.logger.error(f"Failed to schedule weather: {e}")
            raise

    def send_daily_weather(self): # Отправка прогноза
        try:
            forecast = self._get_daily_forecast(DEFAULT_CITY)
            users = self.db.get_subscribed_users()
            for user_id in users:
                try:
                    self.bot.send_message(user_id, forecast, parse_mode='HTML')
                except Exception as e:
                    self.logger.error(f"Failed to send to user {user_id}: {e}")
        except Exception as e:
            self.logger.error(f"Weather job error: {e}")

    # ========== Reminder's Jobs Methods ==========
    def send_event_reminder(self, user_id, event_data):
        try:
            event_time = datetime(
                year=event_data['year'],
                month=int(event_data['month']),
                day=int(event_data['day']),
                hour=int(event_data['time'].split(':')[0]),
                minute=int(event_data['time'].split(':')[1])
            )
            reminder_time = event_time - timedelta(minutes=event_data.get('reminder_offset', 0))
            time_left = event_data.get('reminder_offset', 0)
            time_str = "сейчас" if time_left == 0 else f"{time_left} мин."

            self.bot.send_message(
                user_id,
                f"🔔 Напоминание: {event_data['event_description']}\n"
                f"⏰ Время события: {event_data['time']}\n"
                f"⏳ До события осталось: {time_str}."
            )

            if event_data.get('repeat'):
                next_date = datetime(
                    year=event_data['year'],
                    month=int(event_data['month']),
                    day=int(event_data['day'])
                ) + timedelta(days=event_data['repeat'])

                new_event_id = self.db.add_event(
                    user_id=user_id,
                    year=next_date.year,
                    month=next_date.month,
                    day=next_date.day,
                    time=event_data['time'],
                    description=event_data['event_description'],
                    all_day=event_data.get('all_day', 0),
                    repeat=event_data['repeat'],
                    offset=event_data.get('reminder_offset', 0)
                )

                new_event = self.db.get_event_by_id(new_event_id)
                self.schedule_event_reminder(new_event, user_id)

        except Exception as e:
            self.logger.error(f"Ошибка при отправке напоминания: {e}")

    def schedule_event_reminder(self, event_data, user_id): # Планирование напоминания
        event_time = datetime(
            year=event_data['year'],
            month=int(event_data['month']),
            day=int(event_data['day']),
            hour=int(event_data['time'].split(':')[0]),
            minute=int(event_data['time'].split(':')[1])
        )

        reminder_time = event_time - timedelta(minutes=event_data.get('reminder_offset', 0))
        job_id = f"event_{event_data['id']}"

        try:
            self.scheduler.add_job(
                self.send_event_reminder,
                'date',
                run_date=reminder_time,
                args=[user_id, event_data],
                id=job_id
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to schedule reminder: {e}")
            return False

    def _restore_event_reminders(self): # Восстановление напоминаний из БД при запуске
        events = self.db.get_all_events(only_future=True)
        for event in events:
            event_time = datetime(
                year=event['year'],
                month=int(event['month']),
                day=event['day'],
                hour=int(event['time'].split(':')[0]),
                minute=int(event['time'].split(':')[1])
            )

            job_id = f"event_{event['id']}"
            if event['repeat']:
                self.scheduler.add_job(
                    self.send_event_reminder,
                    'interval',
                    days=1,
                    start_date=event_time,
                    args=[event['user_id'], event],
                    id=job_id
                )
            else:
                self.scheduler.add_job(
                    self.send_event_reminder,
                    'date',
                    run_date=event_time,
                    args=[event['user_id'], event],
                    id=job_id
                )

    def cancel_event_reminder(self, event_id: int) -> bool: # Отмена напоминания
        try:
            self.scheduler.remove_job(f"event_{event_id}")
            return self.db.delete_event(event_id)
        except Exception as e:
            logging.error(f"Failed to cancel event {event_id}: {e}")
            return False


    def stop(self): # Остановка планировщика
        if self._running:
            self.scheduler.shutdown()
            self._running = False
            self.logger.info("Scheduler stopped")