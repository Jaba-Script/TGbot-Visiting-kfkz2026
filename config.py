from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")

# Telegram ID людей, які можуть відмічати відвідуваність
_raw_users = os.getenv("ALLOWED_USERS", "").strip()
ALLOWED_USERS = list(map(int, _raw_users.split(","))) if _raw_users else []
