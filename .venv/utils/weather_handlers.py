import os
import requests
import logging
from datetime import datetime
from config import WEATHER

class Weather_Handlers:
    def get_daily_forecast(self, city_name: str) -> str: # Получение и форматирование прогноза погоды
        base_url = "http://api.openweathermap.org/data/2.5/forecast"
        params = {
            'q': city_name,
            'appid': WEATHER,
            'units': 'metric',
            'cnt': 12,
            'lang': 'ru'
        }

        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        return self.format_forecast(response.json())

    @staticmethod
    def format_forecast(data: dict) -> str: # Форматирование данных прогноза
        try:
            forecast_lines = []
            daytime_temps = []
            for item in data['list']:
                time_obj = datetime.fromtimestamp(item['dt'])
                time_str = time_obj.strftime('%H:%M')
                temp = item['main']['temp']
                desc = item['weather'][0]['description']
                forecast.append(f"🕒 {time}: {temp}°C, {desc.capitalize()}")

                if 8 <= hour < 20:
                    daytime_temps.append(temp)

            if daytime_temps:
                avg_day_temp = sum(daytime_temps) / len(daytime_temps)
                temp_info = f"\n\n<b>Средняя дневная температура (08:00-20:00):</b> {avg_day_temp:.1f}°C"
            else:
                temp_info = "\n\n<b>Дневные данные недоступны</b>"

            return (
                    f"<b>Прогноз в {data['city']['name']}:</b>\n\n" +
                    "\n".join(forecast_lines) +
                    f"\n\n<b>Средняя температура:</b> {temp_info}°C"
            )
        except KeyError as e:
            logging.error(f"Missing key in weather data: {str(e)}")
            raise Exception("Некорректные данные о погоде")

    def format_weather_response(self, data: dict) -> str:
        try:
            weather = data['weather'][0]
            weather_id = weather.get('id')
            main = data['main']
            wind = data['wind']
            sys = data['sys']
            sunrise = datetime.fromtimestamp(sys['sunrise'])
            sunset = datetime.fromtimestamp(sys['sunset'])
        except (KeyError, IndexError) as e:
            return "⚠️ Ошибка при обработке данных о погоде"
        sunrise_time = sunrise.strftime('%H:%M')
        sunset_time = sunset.strftime('%H:%M')

        return (
            f"<b>Погода в {data['name']}:</b>\n\n"
            f"🌡️ Температура: {main['temp']}°C (ощущается как {main['feels_like']}°C)\n"
            f"🌡️ Минимальная/Максимальная температура днем: Минимальная - {main['temp_min']}°C Максимальная - {main['temp_max']}°C)\n"
            f"{self.get_weather_icon(weather_id)} Состояние: {weather['description'].capitalize()}\n"
            f"💧 Влажность: {main['humidity']}%\n"
            f"🌀 Давление: {main['pressure']} hPa\n"
            f"🌬️ Ветер: {wind['speed']} м/с\n"
            f"🌅 Восход: {sunrise_time}\n"
            f"🌇 Закат: {sunset_time}"
        )

    @staticmethod
    def get_weather_icon(weather_id: int) -> str: # Возврат иконки для типа погоды
        if 200 <= weather_id < 300:
            return '⛈️'  # Гроза
        elif 300 <= weather_id < 400:
            return '🌧️'  # Небольшой дождь
        elif 500 <= weather_id < 600:
            return '🌧️'  # Дождь
        elif 600 <= weather_id < 700:
            return '❄️'  # Снег
        elif 700 <= weather_id < 800:
            return '🌫️'  # Атмосферные явления
        elif weather_id == 800:
            return '☀️'  # Ясно
        elif 801 <= weather_id < 900:
            return '☁️'  # Пасмурно
        else:
            return '🌈'

    @staticmethod
    def get_weather_data(city_name: str) -> dict:
        base_url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            'q': city_name,
            'appid': WEATHER,
            'units': 'metric',
            'lang': 'ru'
        }
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        return response.json()