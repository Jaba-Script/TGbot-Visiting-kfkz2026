"""
Запускається ОДИН РАЗ для створення зведеного листа відвідуваності.
Структура: дати по місяцях → підсумок місяця → підсумок семестру → Разом

Використання:
    python setup_summary.py
"""

import gspread
from google.oauth2.service_account import Credentials
from datetime import date, timedelta
import config
from sheet_utils import col_letter, build_columns, make_formula, format_sheet

# ── Налаштування ──────────────────────────────────────────────────────────────
YEAR_START = date(2026, 9, 1)
YEAR_END   = date(2027, 6, 30)
SHEET_NAME = "Зведена"
# ──────────────────────────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_workdays(start: date, end: date) -> list[date]:
    days, cur = [], start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def setup():
    creds  = Credentials.from_service_account_file(config.CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    ss     = client.open_by_key(config.SPREADSHEET_ID)

    students = [s.strip() for s in ss.worksheet("Студенти").col_values(1)[1:] if s.strip()]
    if not students:
        print("❌ Лист 'Студенти' порожній.")
        return

    workdays = get_workdays(YEAR_START, YEAR_END)
    columns  = build_columns(workdays)
    n_cols   = columns[-1]["col"]
    print(f"📅 Робочих днів: {len(workdays)}  |  Студентів: {len(students)}  |  Колонок: {n_cols - 1}")

    try:
        ws = ss.worksheet(SHEET_NAME)
        ws.clear()
        print(f"♻️  Лист '{SHEET_NAME}' очищено.")
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=SHEET_NAME, rows=len(students) + 2, cols=n_cols + 1)
        print(f"✅ Лист '{SHEET_NAME}' створено.")

    header = ["Студент"] + [
        c["date"].strftime("%d.%m.%Y") if c["type"] == "date" else c["name"]
        for c in columns
    ]
    ws.update(range_name="A1", values=[header])
    ws.update(range_name=f"A2:A{len(students) + 1}", values=[[s] for s in students])

    print("⏳ Заповнюю формули...")
    rows_data = [
        [make_formula(c, i + 2) for c in columns]
        for i in range(len(students))
    ]
    ws.update(
        range_name=f"B2:{col_letter(n_cols)}{len(students) + 1}",
        values=rows_data,
        value_input_option="USER_ENTERED",
    )

    print("🎨 Форматування...")
    format_sheet(ss, ws, len(students), n_cols, columns)
    ws.freeze(rows=1, cols=1)

    print(f"\n🎉 Готово! Лист '{SHEET_NAME}' налаштовано.")
    print(f"   Рядків: {len(students)}  |  Стовпців дат: {len(workdays)}  |  Всього: {n_cols - 1}")


if __name__ == "__main__":
    setup()
