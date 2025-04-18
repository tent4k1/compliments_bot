import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from utils.scheduler import ComplimentScheduler


@pytest.fixture
def mock_bot():
    return MagicMock()


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_compliments_count.return_value = 0
    db.get_subscribed_users.return_value = []
    db.get_subscribed_users_count.return_value = 0
    db.get_last_compliment_time.return_value = None
    return db


@pytest.fixture
def scheduler(mock_bot, mock_db):
    return ComplimentScheduler(mock_bot, mock_db)


def test_initialize_default_compliments(scheduler, mock_db):
    # Проверяем инициализацию стандартных комплиментов
    mock_db.get_compliments_count.return_value = 0

    # Сбрасываем mock перед тестом
    mock_db.add_compliment.reset_mock()

    scheduler._initialize_default_compliments()

    # Проверяем, что было 4 вызова (по количеству стандартных комплиментов)
    assert mock_db.add_compliment.call_count == 4

def test_send_compliment_to_user_success(scheduler, mock_bot, mock_db):
    # Проверяем успешную отправку комплимента
    user_id = 123
    mock_db.get_random_compliment.return_value = (1, "Test compliment")

    result = scheduler.send_compliment_to_user(user_id)

    assert result is True
    mock_bot.send_message.assert_called_once_with(user_id, "💖 Комплимент дня:\n\nTest compliment")
    mock_db.record_sent_compliment.assert_called_once_with(user_id, 1)


def test_send_compliment_to_user_no_compliments(scheduler, mock_db):
    # Проверяем случай, когда нет доступных комплиментов
    mock_db.get_random_compliment.return_value = None

    result = scheduler.send_compliment_to_user(123)

    assert result is False


def test_send_compliment_to_user_blocked(scheduler, mock_bot, mock_db):
    # Проверяем обработку заблокированного бота
    user_id = 123
    mock_db.get_random_compliment.return_value = (1, "Test compliment")
    mock_bot.send_message.side_effect = Exception("bot was blocked")

    result = scheduler.send_compliment_to_user(user_id)

    assert result is False
    mock_db.set_subscription.assert_called_once_with(user_id, False)


def test_send_compliments(scheduler, mock_bot, mock_db):
    # Проверяем массовую отправку комплиментов
    mock_db.get_subscribed_users.return_value = [123, 456]
    mock_db.get_random_compliment.return_value = (1, "Group compliment")

    success, total = scheduler.send_compliments()

    assert success == 2
    assert total == 2
    assert mock_bot.send_message.call_count == 2
    mock_db.record_sent_compliment.assert_any_call(123, 1)
    mock_db.record_sent_compliment.assert_any_call(456, 1)


def test_schedule_daily_jobs(scheduler):
    # Проверяем настройку ежедневных заданий
    scheduler.schedule_daily_jobs()

    jobs = scheduler.scheduler.get_jobs()
    assert len(jobs) == 3
    job_ids = {job.id for job in jobs}
    assert job_ids == {'morning_compliment', 'afternoon_compliment', 'evening_compliment'}

def test_start_scheduler(scheduler):
    """Тестируем запуск планировщика"""
    if scheduler.scheduler.running:
        scheduler.scheduler.shutdown()

    scheduler.start()

    assert scheduler._running is True
    assert scheduler.scheduler.running is True


def test_stop_scheduler(scheduler):
    """Тестируем остановку планировщика"""
    if not scheduler.scheduler.running:
        scheduler.scheduler.start()

    scheduler._running = True
    scheduler.stop()

    assert scheduler._running is False
    assert scheduler.scheduler.state == 0  # 0 = STATE_STOPPED

def test_get_status(scheduler, mock_db):
    # Проверяем получение статуса
    mock_db.get_subscribed_users_count.return_value = 5
    mock_db.get_compliments_count.return_value = 10
    mock_db.get_last_compliment_time.return_value = "2023-01-01 12:00:00"

    scheduler._running = True
    status = scheduler.get_status()

    assert status['status'] == 'running'
    assert status['subscribed_users'] == 5
    assert status['active_compliments'] == 10
    assert status['last_sent'] == "2023-01-01 12:00:00"


@patch('utils.scheduler.requests.get')
def test_get_daily_forecast(mock_get, scheduler):
    # Настраиваем mock для requests.get
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'city': {'name': 'Test City'},
        'list': [
            {
                'dt': 1672531200,
                'main': {'temp': 20.5},
                'weather': [{'description': 'clear sky'}]
            }
            for _ in range(8)
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    forecast = scheduler._get_daily_forecast("Test City")

    # Проверяем ключевые элементы в форматированной строке
    assert "<b>🌤️ Прогноз погоды в Test City на сегодня:</b>" in forecast
    assert "03:00: 20.5°C, Clear sky" in forecast
    assert "<b>Средняя дневная температура:</b>" in forecast

def test_check_working(scheduler, mock_db):
    # Проверяем метод проверки состояния
    mock_db.get_subscribed_users_count.return_value = 3
    mock_db.get_compliments_count.return_value = 15
    mock_db.get_last_compliment_time.return_value = "2023-01-01 12:00:00"

    status = scheduler.check_working()

    assert status['status'] == 'stopped'
    assert status['users_count'] == 3
    assert status['compliments_available'] == 15
    assert status['last_compliment_sent'] == "2023-01-01 12:00:00"