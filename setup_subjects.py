import time
"""
Запускається після заповнення листа Schedule.
Читає предмети з розкладу і створює по одному листу на кожен предмет.

Використання:
    python setup_subjects.py
"""

import gspread
from google.oauth2.service_account import Credentials
from datetime import date, timedelta
import config

# ── Налаштування ──────────────────────────────────────────────────────────────
YEAR_START = date(2026, 9, 1)
YEAR_END   = date(2027, 6, 30)

SEMESTER_1 = {9, 10, 11, 12}
SEMESTER_2 = {1, 2, 3, 4, 5, 6}

UA_MONTHS = {
    1: "Січень",  2: "Лютий",    3: "Березень", 4: "Квітень",
    5: "Травень", 6: "Червень",  7: "Липень",   8: "Серпень",
    9: "Вересень",10: "Жовтень", 11: "Листопад",12: "Грудень",
}
DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт"]
# ──────────────────────────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def col_letter(n: int) -> str:
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def get_subject_dates(weekdays: set, start: date, end: date) -> list[date]:
    """Всі дати в діапазоні, де день тижня є в weekdays."""
    days, cur = [], start
    while cur <= end:
        if cur.weekday() in weekdays:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def read_schedule(ss) -> dict[str, set]:
    """Повертає {назва_предмету: {weekday_idx, ...}} з листа Schedule."""
    data = ss.worksheet("Schedule").get_all_values()
    subjects: dict[str, set] = {}
    for row in data[1:]:
        for day_i in range(5):
            if len(row) > day_i + 1:
                subj = row[day_i + 1].strip()
                if subj and subj not in ("-", "—", ""):
                    subjects.setdefault(subj, set()).add(day_i)
    return subjects


def build_columns(dates: list[date]) -> list[dict]:
    months: dict[tuple, list[date]] = {}
    for d in dates:
        months.setdefault((d.year, d.month), []).append(d)

    columns, sem1_cols, sem2_cols = [], [], []
    col_idx = 2

    for (_, m), days in sorted(months.items()):
        date_cols = []
        for d in days:
            columns.append({"type": "date", "date": d, "col": col_idx})
            date_cols.append(col_idx)
            col_idx += 1

        columns.append({"type": "month_total", "name": UA_MONTHS[m],
                        "date_cols": date_cols, "col": col_idx})
        (sem1_cols if m in SEMESTER_1 else sem2_cols).append(col_idx)
        col_idx += 1

        if m == 12:
            columns.append({"type": "semester_total", "name": "1 Семестр",
                            "month_cols": sem1_cols[:], "col": col_idx})
            col_idx += 1
        if m == 6:
            columns.append({"type": "semester_total", "name": "2 Семестр",
                            "month_cols": sem2_cols[:], "col": col_idx})
            col_idx += 1

    all_sem = [c["col"] for c in columns if c["type"] == "semester_total"]
    columns.append({"type": "grand_total", "name": "Разом",
                    "sem_cols": all_sem, "col": col_idx})
    return columns


def make_formula(col_desc: dict, row: int, subject: str) -> str:
    t, c = col_desc["type"], col_letter(col_desc["col"])
    if t == "date":
        return (f'=COUNTIFS(Log!$E:$E;$A{row};Log!$A:$A;{c}$1;'
                f'Log!$D:$D;"{subject}")*2')
    elif t == "month_total":
        cols = col_desc["date_cols"]
        return f"=SUM({col_letter(cols[0])}{row}:{col_letter(cols[-1])}{row})"
    elif t in ("semester_total", "grand_total"):
        key = "month_cols" if t == "semester_total" else "sem_cols"
        parts = "+".join(f"{col_letter(mc)}{row}" for mc in col_desc[key])
        return f"={parts}"
    return ""


def setup_subject_sheet(ss, subject: str, weekdays: set, students: list):
    dates   = get_subject_dates(weekdays, YEAR_START, YEAR_END)
    columns = build_columns(dates)
    n_cols  = columns[-1]["col"]

    try:
        ws = ss.worksheet(subject)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=subject, rows=len(students) + 2, cols=n_cols + 1)

    header = ["Студент"] + [
        c["date"].strftime("%d.%m.%Y") if c["type"] == "date" else c["name"]
        for c in columns
    ]
    ws.update(range_name="A1", values=[header])
    ws.update(range_name=f"A2:A{len(students) + 1}", values=[[s] for s in students])

    rows_data = [
        [make_formula(c, i + 2, subject) for c in columns]
        for i in range(len(students))
    ]
    ws.update(
        range_name=f"B2:{col_letter(n_cols)}{len(students) + 1}",
        values=rows_data,
        value_input_option="USER_ENTERED",
    )

    summary_cols = [c["col"] - 1 for c in columns
                    if c["type"] in ("month_total", "semester_total", "grand_total")]
    requests = [{"repeatCell": {
        "range": {"sheetId": ws.id, "startRowIndex": 1,
                  "endRowIndex": len(students) + 1,
                  "startColumnIndex": 1, "endColumnIndex": n_cols},
        "cell": {"userEnteredFormat": {
            "numberFormat": {"type": "NUMBER", "pattern": '[=0]"";General'}}},
        "fields": "userEnteredFormat.numberFormat",
    }}]
    for ci in summary_cols:
        requests.append({"repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 0,
                      "endRowIndex": len(students) + 1,
                      "startColumnIndex": ci, "endColumnIndex": ci + 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold",
        }})
    ss.batch_update({"requests": requests})
    ws.freeze(rows=1, cols=1)

    print(f"  ✅ '{subject}': {len(dates)} дат, {n_cols - 1} колонок")


def setup():
    creds  = Credentials.from_service_account_file(config.CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    ss     = client.open_by_key(config.SPREADSHEET_ID)

    students = [s.strip() for s in ss.worksheet("Студенти").col_values(1)[1:] if s.strip()]
    if not students:
        print("❌ Лист 'Студенти' порожній.")
        return

    subjects = read_schedule(ss)
    if not subjects:
        print("❌ Лист 'Schedule' порожній або не заповнений.")
        return

    print(f"📚 Знайдено предметів: {len(subjects)}")
    for subj, wdays in subjects.items():
        print(f"  • {subj} ({', '.join(DAY_NAMES[d] for d in sorted(wdays))})")
    print()

    for i, (subject, weekdays) in enumerate(subjects.items()):
        print(f"Обробляю '{subject}'...")
        setup_subject_sheet(ss, subject, weekdays, students)
        if i < len(subjects) - 1:
            print("  ⏳ Пауза 20 сек (ліміт API)...")
            time.sleep(20)

    print(f"\n🎉 Готово! Створено/оновлено {len(subjects)} листів.")


if __name__ == "__main__":
    setup()
