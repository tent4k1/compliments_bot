import unittest
from unittest.mock import MagicMock, patch, call
from scheduler import ComplimentScheduler
from database import Database


class TestComplimentScheduler(unittest.TestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.db = MagicMock(spec=Database)
        self.scheduler = ComplimentScheduler(bot=self.bot, db=self.db)

        # Настройка моков для базы данных
        self.db.get_subscribed_users.return_value = {123, 456}
        self.db.get_random_compliment.return_value = (1, "Тестовый комплимент")
        self.db.record_sent_compliment.return_value = True

    def test_schedule_jobs(self):
        """Тест настройки расписания отправки (упрощенная версия)"""
        with patch('apscheduler.schedulers.background.BackgroundScheduler.add_job') as mock_add_job:
            self.scheduler.schedule_daily_jobs()

            # Проверяем что было 3 вызова
            self.assertEqual(mock_add_job.call_count, 3)

            # Проверяем что все вызовы содержат send_compliments
            for call_args in mock_add_job.call_args_list:
                self.assertEqual(call_args[0][0], self.scheduler.send_compliments)

    def test_send_compliments_with_users(self):
        """Тест отправки с подписанными пользователями"""
        result = self.scheduler.send_compliments()

        # Проверяем результат
        self.assertEqual(result, (2, 2))

        # Проверяем отправку сообщений
        expected_calls = [
            call(123, "✨ Тестовый комплимент"),
            call(456, "✨ Тестовый комплимент")
        ]
        self.bot.send_message.assert_has_calls(expected_calls, any_order=True)

        # Проверяем запись в БД
        self.db.record_sent_compliment.assert_has_calls([
            call(123, 1),
            call(456, 1)
        ], any_order=True)

    def test_send_compliments_no_users(self):
        """Тест отправки без пользователей"""
        self.db.get_subscribed_users.return_value = set()
        result = self.scheduler.send_compliments()
        self.assertEqual(result, (0, 0))
        self.bot.send_message.assert_not_called()

    def test_send_compliments_no_compliments(self):
        """Тест случая когда нет комплиментов"""
        self.db.get_random_compliment.return_value = None
        result = self.scheduler.send_compliments()
        self.assertEqual(result, (0, 2))
        self.bot.send_message.assert_not_called()

    def test_start_stop(self):
        """Тест запуска и остановки планировщика"""
        with patch.object(self.scheduler.scheduler, 'start') as mock_start, \
                patch.object(self.scheduler.scheduler, 'shutdown') as mock_stop:
            self.scheduler.start()
            mock_start.assert_called_once()

            self.scheduler.stop()
            mock_stop.assert_called_once()


if __name__ == '__main__':
    unittest.main()