"""
Скрипт для заповнення листа Log тестовими даними.
Запускається вручну для перевірки зведеної таблиці.

Використання:
    python test_data.py         — додати тестові дані
    python test_data.py --clear — очистити Log (залишити тільки заголовок)
"""

import sys
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, timedelta
import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ── Тестові дані ──────────────────────────────────────────────────────────────
# Підстав реальні імена зі свого листа "Студенти"
TEST_ABSENCES = [
    # (дата,        день,  пара, предмет,       студент,              статус)
    ("01.09.2026", "Пн",  "1", "Математика",   "Бабчук І. О.",   "Відсутній"),
    ("01.09.2026", "Пн",  "1", "Математика",   "Калуга Н. В.",     "Відсутній"),
    ("01.09.2026", "Пн",  "2", "Фізика",       "Боровик П. Д.",   "Відсутній"),
    ("03.09.2026", "Ср",  "1", "Фізика",       "Любенко Н. В.",   "Відсутній"),
    ("03.09.2026", "Ср",  "3", "Англійська",   "Калуга Н. В.",     "Відсутній"),
    ("05.09.2026", "Пт",  "2", "Математика",   "Бабчук І. О.",   "Відсутній"),
    ("08.09.2026", "Пн",  "1", "Математика",   "Любенко Н. В.",   "Відсутній"),
    ("08.09.2026", "Пн",  "1", "Математика",   "Калуга Н. В.",     "Відсутній"),
    ("10.09.2026", "Ср",  "2", "Фізика",       "Бабчук І. О.",   "Відсутній"),
]
# ──────────────────────────────────────────────────────────────────────────────

MARKED_BY = "Тест"
TEST_TIME  = "10:00:00"


def get_worksheet():
    creds = Credentials.from_service_account_file(config.CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    ss = client.open_by_key(config.SPREADSHEET_ID)
    return ss.worksheet("Log")


def clear_log():
    ws = get_worksheet()
    # Залишаємо тільки заголовок (рядок 1)
    all_values = ws.get_all_values()
    if len(all_values) > 1:
        ws.delete_rows(2, len(all_values))
    print(f"🗑  Log очищено. Залишився тільки заголовок.")


def add_test_data():
    ws = get_worksheet()

    rows = [
        [date, day, pair, subject, student, status, MARKED_BY, TEST_TIME]
        for date, day, pair, subject, student, status in TEST_ABSENCES
    ]

    ws.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"✅ Додано {len(rows)} тестових рядків у Log.")
    print(f"\nСтуденти в тесті:")
    unique_students = sorted(set(r[4] for r in TEST_ABSENCES))
    for s in unique_students:
        count = sum(1 for r in TEST_ABSENCES if r[4] == s)
        print(f"  • {s} — {count} пропусків ({count * 2} год)")
    print(f"\nПеревір лист 'Зведена' — там мають з'явитись числа.")


if __name__ == "__main__":
    if "--clear" in sys.argv:
        clear_log()
    else:
        add_test_data()
