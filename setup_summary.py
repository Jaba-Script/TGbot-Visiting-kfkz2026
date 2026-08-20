"""
Запускається ОДИН РАЗ для створення зведеного листа відвідуваності.
Створює лист "Зведена" з рядками-студентами і стовпцями-датами.

Використання:
    python setup_summary.py
"""

import gspread
from google.oauth2.service_account import Credentials
from datetime import date, timedelta
import config

# ── Налаштування навчального року ─────────────────────────────────────────────
YEAR_START = date(2026, 9, 1)   # початок навчального року
YEAR_END   = date(2027, 6, 30)  # кінець навчального року
SHEET_NAME = "Зведена"
# ──────────────────────────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_workdays(start: date, end: date) -> list[date]:
    """Повертає всі робочі дні (пн–пт) між start і end включно."""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # 0=Пн ... 4=Пт
            days.append(current)
        current += timedelta(days=1)
    return days


def setup():
    creds = Credentials.from_service_account_file(config.CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    ss = client.open_by_key(config.SPREADSHEET_ID)

    # ── Студенти ───────────────────────────────────────────────────────────────
    students_ws = ss.worksheet("Студенти")
    students = [s.strip() for s in students_ws.col_values(1)[1:] if s.strip()]
    if not students:
        print("❌ Лист 'Студенти' порожній. Спочатку заповни його.")
        return

    # ── Робочі дні ────────────────────────────────────────────────────────────
    workdays = get_workdays(YEAR_START, YEAR_END)
    print(f"📅 Робочих днів: {len(workdays)}  |  Студентів: {len(students)}")

    # ── Створити або очистити лист ────────────────────────────────────────────
    try:
        ws = ss.worksheet(SHEET_NAME)
        ws.clear()
        print(f"♻️  Лист '{SHEET_NAME}' очищено.")
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(
            title=SHEET_NAME,
            rows=len(students) + 2,
            cols=len(workdays) + 3,
        )
        print(f"✅ Лист '{SHEET_NAME}' створено.")

    # ── Заголовки рядків (студенти) ───────────────────────────────────────────
    # Колонка A: "Студент", потім імена
    student_col = [["Студент"]] + [[s] for s in students]
    ws.update(
        range_name=f"A1:A{len(student_col)}",
        values=student_col,
    )

    # ── Заголовки стовпців (дати) + "Разом" ───────────────────────────────────
    # Рядок 1: порожньо (A1 вже "Студент"), потім дати, потім "Разом"
    date_headers = [[d.strftime("%d.%m.%Y") for d in workdays] + ["Разом"]]
    ws.update(
        range_name=f"B1:{gspread.utils.rowcol_to_a1(1, len(workdays) + 2)}",
        values=date_headers,
    )

    # ── Формули для кожного студента ──────────────────────────────────────────
    # Для кожного дня: =COUNTIFS(Log!$E:$E, $A2, Log!$A:$A, B$1) * 2
    # Log колонки: A=Дата, E=Студент
    print("⏳ Заповнюю формули...")

    rows_data = []
    for row_i, _ in enumerate(students):
        sheet_row = row_i + 2  # рядок в таблиці (з урахуванням заголовка)
        row = []
        for col_i in range(len(workdays)):
            col_letter = gspread.utils.rowcol_to_a1(sheet_row, col_i + 2)[:-1]  # напр. "B"
            formula = (
                f'=IFERROR(COUNTIFS(Log!$E:$E,$A{sheet_row},'
                f'Log!$A:$A,{col_letter}$1)*2,0)'
            )
            row.append(formula)
        # Стовпець "Разом" — сума по рядку
        start_col = gspread.utils.rowcol_to_a1(sheet_row, 2)[:-1]
        end_col   = gspread.utils.rowcol_to_a1(sheet_row, len(workdays) + 1)[:-1]
        row.append(f"=SUM({start_col}{sheet_row}:{end_col}{sheet_row})")
        rows_data.append(row)

    # Записуємо всі формули одним запитом
    start_cell = gspread.utils.rowcol_to_a1(2, 2)
    end_cell   = gspread.utils.rowcol_to_a1(len(students) + 1, len(workdays) + 2)
    ws.update(
        range_name=f"{start_cell}:{end_cell}",
        values=rows_data,
        value_input_option="USER_ENTERED",  # щоб формули виконувались
    )

    # ── Заморозити перший рядок і стовпець ────────────────────────────────────
    ws.freeze(rows=1, cols=1)

    print(f"\n🎉 Готово! Лист '{SHEET_NAME}' налаштовано.")
    print(f"   Рядків: {len(students)}  |  Стовпців дат: {len(workdays)}  |  + стовпець 'Разом'")
    print(f"   Відкрий таблицю і перевір!")


if __name__ == "__main__":
    setup()
