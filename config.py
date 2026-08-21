from dotenv import load_dotenv
from datetime import datetime
import os

load_dotenv()

BOT_TOKEN        = os.getenv("BOT_TOKEN")
SPREADSHEET_ID   = os.getenv("SPREADSHEET_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
ALLOWED_USERS    = []

_raw = os.getenv("ALLOWED_USERS", "").strip()
if _raw:
    ALLOWED_USERS = list(map(int, _raw.split(",")))

# Дата початку тижня "А" (будь-який понеділок тижня А у форматі ДД.ММ.РРРР)
# Якщо не вказано — розклад вважається однаковим щотижня
_week_a = os.getenv("WEEK_A_START", "").strip()
WEEK_A_START = None
if _week_a:
    try:
        WEEK_A_START = datetime.strptime(_week_a, "%d.%m.%Y").date()
    except ValueError:
        print(f"⚠️  WEEK_A_START невірний формат: '{_week_a}'. Очікується ДД.ММ.РРРР")
