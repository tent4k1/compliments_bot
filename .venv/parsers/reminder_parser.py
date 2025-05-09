import logging
import re
from datetime import datetime, timedelta
from dateutil.parser import parse
from typing import Optional

class ReminderParser:
    def __init__(self):
        """Инициализация, паттерны команд"""
        self.date_pattern = r"(\d{1,2})\s*(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s*(\d{4})?"
        self.time_pattern = r"(\d{1,2}):(\d{2})"
        self.relative_time_pattern = r"(через|за)\s*(\d+)\s*(минут|час|дней|день)"

        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.DEBUG)

    def parse_date(self, date_str: str) -> Optional[datetime]:
        """Парсинг даты"""
        try:
            return parse(date_str, dayfirst=True)
        except ValueError:
            return None

    def extract_date(self, text: str) -> Optional[datetime]:
        """Извлечение даты"""
        match = re.search(self.date_pattern, text.lower())
        if match:
            day, month_name, year = match.groups()
            month_number = self.month_name_to_number(month_name)
            day = int(day)
            year = int(year) if year else datetime.now().year
            return datetime(year, month_number, day)
        return None

    def extract_time(self, text: str) -> Optional[str]:
        """Извлечение времени"""
        match = re.search(self.time_pattern, text)
        if match:
            return match.group(0)
        return None

    def extract_relative_time(self, text: str) -> Optional[timedelta]:
        """Извлечение относительного времени (за час, через час и т.д.)"""
        match = re.search(self.relative_time_pattern, text.lower())
        if match:
            direction, value, unit = match.groups()
            value = int(value)
            if 'час' in unit:
                return timedelta(hours=value)
            elif 'минут' in unit:
                return timedelta(minutes=value)
            elif 'день' in unit:
                return timedelta(days=value)
        return None

    def month_name_to_number(self, month_name: str) -> int:
        """Приведение месяцев к числам"""
        months = {
            "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5,
            "июня": 6, "июля": 7, "августа": 8, "сентября": 9, "октября": 10,
            "ноября": 11, "декабря": 12
        }
        return months.get(month_name.lower(), 0)

    def remove_date_and_time(self, text: str, date: Optional[datetime], time: Optional[str],
                             offset: Optional[timedelta]) -> str:
        """Очистка даты и времени из описания"""
        cleaned_text = text.lower()

        if date:
            months_reverse = {v: k for k, v in {
                "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5,
                "июня": 6, "июля": 7, "августа": 8, "сентября": 9, "октября": 10,
                "ноября": 11, "декабря": 12
            }.items()}

            day = date.day
            month_name = months_reverse.get(date.month, "")
            year = str(date.year)

            date_pattern = rf"{day}\s*{month_name}(?:\s*{year})?"
            cleaned_text = re.sub(date_pattern, "", cleaned_text)

        if time:
            cleaned_text = cleaned_text.replace(time, "")

        if offset:
            cleaned_text = re.sub(r"(за|через)\s*\d+\s*(минут[аы]?|час[а]?|дней?|день)", "", cleaned_text)

        cleaned_text = re.sub(r"\b(напомни|мне|пожалуйста|когда|нужно|надо)\b", "", cleaned_text)
        cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()

        return cleaned_text

    def parse_event(self, command: str) -> dict | None:
        """Основной модуль парсинга"""
        try:
            command = command.strip().lower()
            self.logger.debug(f"Команда для парсинга: {command}")

            rel_match = re.search(self.relative_time_pattern, command)
            if rel_match:
                direction, value, unit = rel_match.groups()
                value = int(value)
                offset_minutes = self.unit_to_minutes(value, unit)

                event_time = datetime.now() + timedelta(minutes=offset_minutes)
                date = event_time.date()
                time = event_time.time()

                description = self.clean_description(command[:rel_match.start()])
                self.logger.debug(f"Распознана относительная дата: {date}, время: {time}")
                return {
                    "date": datetime(date.year, date.month, date.day),
                    "year": date.year,
                    "month": date.month,
                    "day": date.day,
                    "time": time.strftime("%H:%M"),
                    "event_description": description,
                    "reminder_offset": 0,
                    "all_day": 0,
                    "repeat": 0,
                }

            date_match = re.search(self.date_pattern, command)
            if date_match:
                day, month_str, year = date_match.groups()
                self.logger.debug(f"Найдена дата: {day} {month_str} {year}")

                month = self.month_name_to_number(month_str)
                year = int(year) if year else datetime.now().year

                time_match = re.search(self.time_pattern, command)
                if time_match:
                    hour, minute = map(int, time_match.groups())
                    time_str = f"{hour:02}:{minute:02}"
                    self.logger.debug(f"Найдено время: {time_str}")
                else:
                    time_str = "08:00"

                description = self.clean_description(command[:min(date_match.start(), time_match.start())])
                return {
                    "date": datetime(year, month, int(day)),
                    "year": year,
                    "month": month,
                    "day": int(day),
                    "time": time_str,
                    "event_description": description,
                    "reminder_offset": 0,
                    "all_day": int(not time_match),
                    "repeat": 0,
                }

            self.logger.warning(f"Не удалось найти дату в команде: {command}")
            return None
        except Exception as e:
            self.logger.error(f"[parse_event] Ошибка при парсинге команды: {e}")
            return None

    def unit_to_minutes(self, value, unit):
        """Приведение времени к минутам"""
        if "минут" in unit:
            return value
        if "час" in unit:
            return value * 60
        if "день" in unit:
            return value * 1440
        return 0

    def clean_description(self, text):
        """Очистка описания от лишнего"""
        text = re.sub(r"\b(напомни|пожалуйста|надо|мне|нужно|напомнить)\b", "", text)
        text = re.sub(r"\bв\b$", "", text.strip())  # удаляет "в" на конце
        return text.strip()

    def extract_description(self, text: str) -> Optional[str]:
        """Извлечение описания из текста"""
        date_part = re.search(self.date_pattern, text.lower())
        time_part = re.search(self.time_pattern, text)

        if date_part:
            text = text.replace(date_part.group(0), "")
        if time_part:
            text = text.replace(time_part.group(0), "")

        return text.strip() if text.strip() else None
