import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
WEATHER = os.getenv("WEATHER_API")
DEFAULT_CITY = "Москва"
ADMIN_ID = 7522466558
MIUS_ID = 5236847464

DB_PATH = BASE_DIR / 'data' / 'bot_database.db'

COMPLIMENTS_FILE = BASE_DIR / "data" / "compliments.txt"
SENT_COMPLIMENTS_FILE = BASE_DIR / "data" / "sent_compliments.txt"

COMPLIMENTS_FILE = "data/compliments.txt"

INTERVALS = [
    (8, 10),
    (13, 15),
    (20, 22)
]

CHECK_INTERVAL = 60