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

# ── Налаштування ──────────────────────────────────────────────────────────────
YEAR_START = date(2026, 9, 1)
YEAR_END   = date(2027, 6, 30)
SHEET_NAME = "Зведена"

# Місяці першого і другого семестрів
SEMESTER_1 = {9, 10, 11, 12}       # вересень–грудень
SEMESTER_2 = {1, 2, 3, 4, 5, 6}   # січень–червень

UA_MONTHS = {
    1: "Січень", 2: "Лютий",   3: "Березень", 4: "Квітень",
    5: "Травень", 6: "Червень", 7: "Липень",   8: "Серпень",
    9: "Вересень", 10: "Жовтень", 11: "Листопад", 12: "Грудень",
}
# ──────────────────────────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def col_letter(n: int) -> str:
    """Індекс колонки (1-based) → літера. 1→A, 27→AA тощо."""
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def get_workdays(start: date, end: date) -> list[date]:
    days, cur = [], start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def build_columns(workdays: list[date]) -> list[dict]:
    """
    Будує список дескрипторів колонок:
      date          — звичайна дата
      month_total   — підсумок місяця
      semester_total— підсумок семестру
      grand_total   — підсумок року
    """
    # Групуємо робочі дні по місяцях (зберігаємо порядок)
    months: dict[tuple, list[date]] = {}
    for d in workdays:
        key = (d.year, d.month)
        months.setdefault(key, []).append(d)

    columns = []
    sem1_month_cols: list[int] = []   # індекси колонок місячних підсумків сем.1
    sem2_month_cols: list[int] = []
    col_idx = 2  # починаємо з колонки B

    for (year, month), days in sorted(months.items()):
        # Дати місяця
        month_date_cols: list[int] = []
        for d in days:
            columns.append({"type": "date", "date": d, "col": col_idx})
            month_date_cols.append(col_idx)
            col_idx += 1

        # Підсумок місяця
        columns.append({
            "type": "month_total",
            "name": UA_MONTHS[month],
            "date_cols": month_date_cols,
            "col": col_idx,
        })
        (sem1_month_cols if month in SEMESTER_1 else sem2_month_cols).append(col_idx)
        col_idx += 1

        # Після останнього місяця семестру — вставляємо підсумок семестру
        if month == 12:  # кінець 1-го семестру
            columns.append({
                "type": "semester_total",
                "name": "1 Семестр",
                "month_cols": sem1_month_cols[:],
                "col": col_idx,
            })
            col_idx += 1

        if month == 6:   # кінець 2-го семестру
            columns.append({
                "type": "semester_total",
                "name": "2 Семестр",
                "month_cols": sem2_month_cols[:],
                "col": col_idx,
            })
            col_idx += 1

    # Загальний підсумок
    all_sem_cols = [c["col"] for c in columns if c["type"] == "semester_total"]
    columns.append({"type": "grand_total", "name": "Разом", "sem_cols": all_sem_cols, "col": col_idx})

    return columns


def make_formula(col_desc: dict, row: int) -> str:
    t = col_desc["type"]
    c = col_letter(col_desc["col"])

    if t == "date":
        # Рахуємо пропуски з Log: E=студент, A=дата
        return (
            f"=COUNTIFS(Log!$E:$E;$A{row};Log!$A:$A;{c}$1)*2"
        )
    elif t == "month_total":
        # Сума дат цього місяця (вони йдуть підряд → можна SUM діапазоном)
        cols = col_desc["date_cols"]
        start, end = col_letter(cols[0]), col_letter(cols[-1])
        return f"=SUM({start}{row}:{end}{row})"

    elif t == "semester_total":
        # Сума місячних підсумків (можуть йти не підряд через вставки)
        parts = "+".join(f"{col_letter(mc)}{row}" for mc in col_desc["month_cols"])
        return f"={parts}"

    elif t == "grand_total":
        parts = "+".join(f"{col_letter(sc)}{row}" for sc in col_desc["sem_cols"])
        return f"={parts}"

    return ""


def setup():
    creds = Credentials.from_service_account_file(config.CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    ss = client.open_by_key(config.SPREADSHEET_ID)

    students = [s.strip() for s in ss.worksheet("Студенти").col_values(1)[1:] if s.strip()]
    if not students:
        print("❌ Лист 'Студенти' порожній.")
        return

    workdays = get_workdays(YEAR_START, YEAR_END)
    columns  = build_columns(workdays)
    n_cols   = columns[-1]["col"]
    print(f"📅 Робочих днів: {len(workdays)}  |  Студентів: {len(students)}  |  Всього колонок: {n_cols - 1}")

    # ── Створити / очистити лист ──────────────────────────────────────────────
    try:
        ws = ss.worksheet(SHEET_NAME)
        ws.clear()
        print(f"♻️  Лист '{SHEET_NAME}' очищено.")
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=SHEET_NAME, rows=len(students) + 2, cols=n_cols + 1)
        print(f"✅ Лист '{SHEET_NAME}' створено.")

    # ── Заголовки ─────────────────────────────────────────────────────────────
    header = ["Студент"] + [
        c["date"].strftime("%d.%m.%Y") if c["type"] == "date" else c["name"]
        for c in columns
    ]
    ws.update(range_name="A1", values=[header])

    # Імена студентів
    ws.update(
        range_name=f"A2:A{len(students) + 1}",
        values=[[s] for s in students],
    )

    # ── Формули ───────────────────────────────────────────────────────────────
    print("⏳ Заповнюю формули...")
    rows_data = []
    for i, _ in enumerate(students):
        row_num = i + 2
        rows_data.append([make_formula(c, row_num) for c in columns])

    end_cell = f"{col_letter(n_cols)}{len(students) + 1}"
    ws.update(
        range_name=f"B2:{end_cell}",
        values=rows_data,
        value_input_option="USER_ENTERED",
    )

    # ── Числовий формат: ховаємо нулі ─────────────────────────────────────────
    ss.batch_update({"requests": [{
        "repeatCell": {
            "range": {
                "sheetId": ws.id,
                "startRowIndex": 1,
                "endRowIndex": len(students) + 1,
                "startColumnIndex": 1,
                "endColumnIndex": n_cols,
            },
            "cell": {"userEnteredFormat": {
                "numberFormat": {"type": "NUMBER", "pattern": '[=0]"";General'}
            }},
            "fields": "userEnteredFormat.numberFormat",
        }
    }]})

    # ── Жирний шрифт для підсумкових колонок ─────────────────────────────────
    summary_col_indices = [
        c["col"] - 1  # 0-based для API
        for c in columns
        if c["type"] in ("month_total", "semester_total", "grand_total")
    ]
    bold_requests = []
    for ci in summary_col_indices:
        bold_requests.append({"repeatCell": {
            "range": {
                "sheetId": ws.id,
                "startRowIndex": 0,
                "endRowIndex": len(students) + 1,
                "startColumnIndex": ci,
                "endColumnIndex": ci + 1,
            },
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold",
        }})
    if bold_requests:
        ss.batch_update({"requests": bold_requests})

    # ── Заморозити ────────────────────────────────────────────────────────────
    ws.freeze(rows=1, cols=1)

    print(f"\n🎉 Готово!")
    print(f"   Дат: {len(workdays)}  |  Місячних підсумків: {len([c for c in columns if c['type']=='month_total'])}")
    print(f"   Семестрів: {len([c for c in columns if c['type']=='semester_total'])}")


if __name__ == "__main__":
    setup()
