import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Назви днів тижня для читання колонок розкладу
DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт"]


def get_client():
    creds = Credentials.from_service_account_file(
        config.CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(creds)


def get_spreadsheet():
    client = get_client()
    return client.open_by_key(config.SPREADSHEET_ID)


def get_schedule_for_today() -> list[tuple[str, str]]:
    """
    Повертає список (номер_пари, предмет) для поточного дня.
    Читає лист 'Schedule' кожного разу свіжо.
    """
    day_idx = datetime.now().weekday()
    if day_idx >= 5:  # субота або неділя
        return []

    ss = get_spreadsheet()
    sheet = ss.worksheet("Schedule")
    data = sheet.get_all_values()

    # Формат: рядок 0 = заголовки [Пара, Пн, Вт, Ср, Чт, Пт]
    # day_idx + 1 = колонка для поточного дня
    col_idx = day_idx + 1

    pairs = []
    for row in data[1:]:  # пропускаємо заголовок
        if len(row) <= col_idx:
            continue
        pair_num = row[0].strip()
        subject = row[col_idx].strip()
        if pair_num and subject and subject not in ("—", "-", ""):
            pairs.append((pair_num, subject))

    return pairs


def get_students() -> list[str]:
    """
    Повертає список студентів з листа 'Студенти'.
    Колонка A, перший рядок — заголовок 'Студент'.
    """
    ss = get_spreadsheet()
    sheet = ss.worksheet("Студенти")
    values = sheet.col_values(1)[1:]  # пропускаємо заголовок
    return [s.strip() for s in values if s.strip()]


def log_absences(
    date: str,
    pair_num: str,
    subject: str,
    absent_students: list[str],
    marked_by: str,
) -> None:
    """
    Записує відсутніх студентів у лист 'Log'.
    Кожен студент — окремий рядок.
    """
    if not absent_students:
        return

    ss = get_spreadsheet()
    log_sheet = ss.worksheet("Log")

    timestamp = datetime.now().strftime("%H:%M:%S")
    day_name = DAY_NAMES[datetime.now().weekday()]

    rows = [
        [date, day_name, pair_num, subject, student, "Відсутній", marked_by, timestamp]
        for student in absent_students
    ]

    log_sheet.append_rows(rows, value_input_option="USER_ENTERED")
