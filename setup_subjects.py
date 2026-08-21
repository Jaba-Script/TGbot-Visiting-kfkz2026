"""
Запускається після заповнення листа Schedule.
Читає предмети з розкладу і створює по одному листу на кожен предмет.

Підтримує чергування тижнів А/Б якщо Schedule має стовпець «Тиждень».

Використання:
    python setup_subjects.py
"""

import time
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, timedelta
import config
from sheet_utils import col_letter, build_columns, make_formula, format_sheet

# ── Налаштування ──────────────────────────────────────────────────────────────
YEAR_START = date(2026, 9, 1)
YEAR_END   = date(2027, 6, 30)
DAY_NAMES  = ["Пн", "Вт", "Ср", "Чт", "Пт"]
# ──────────────────────────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_week_type(d: date) -> str:
    """'А' або 'Б' для конкретної дати. Якщо WEEK_A_START не вказано → 'А' для всіх."""
    if not config.WEEK_A_START:
        return "А"
    return "А" if (d - config.WEEK_A_START).days // 7 % 2 == 0 else "Б"


def get_subject_dates(week_a_days: set, week_b_days: set,
                      start: date, end: date) -> list[date]:
    """
    Генерує дати занять з предмету з урахуванням чергування тижнів.
    week_a_days / week_b_days — множини індексів днів тижня (0=Пн).
    """
    days, cur = [], start
    while cur <= end:
        wtype   = get_week_type(cur)
        weekdays = week_a_days if wtype == "А" else week_b_days
        if cur.weekday() in weekdays:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def read_schedule(ss) -> tuple[dict, bool]:
    """
    Читає Schedule і повертає:
      ({предмет: {"А": {weekday_idx,...}, "Б": {weekday_idx,...}}}, alternating: bool)

    Формат без чергування:  [Пара | Пн | Вт | Ср | Чт | Пт]
    Формат з чергуванням:  [Тиждень | Пара | Пн | Вт | Ср | Чт | Пт]
    """
    data = ss.worksheet("Schedule").get_all_values()
    alternating = data[0][0].strip() == "Тиждень"
    subjects: dict[str, dict] = {}

    if alternating:
        for row in data[1:]:
            if len(row) < 2:
                continue
            tyzh = row[0].strip()
            if tyzh not in ("А", "Б"):
                continue
            for day_i in range(5):
                if len(row) > day_i + 2:
                    subj = row[day_i + 2].strip()
                    if subj and subj not in ("-", "—", ""):
                        if subj not in subjects:
                            subjects[subj] = {"А": set(), "Б": set()}
                        subjects[subj][tyzh].add(day_i)
    else:
        for row in data[1:]:
            for day_i in range(5):
                if len(row) > day_i + 1:
                    subj = row[day_i + 1].strip()
                    if subj and subj not in ("-", "—", ""):
                        if subj not in subjects:
                            subjects[subj] = {"А": set(), "Б": set()}
                        subjects[subj]["А"].add(day_i)
                        subjects[subj]["Б"].add(day_i)  # однаково для обох тижнів

    return subjects, alternating


def setup_subject_sheet(ss, subject: str, week_days: dict, students: list):
    dates   = get_subject_dates(week_days["А"], week_days["Б"], YEAR_START, YEAR_END)
    if not dates:
        print(f"  ⚠️  Для '{subject}' не знайдено дат — пропускаємо.")
        return

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

    format_sheet(ss, ws, len(students), n_cols, columns)
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

    subjects, alternating = read_schedule(ss)
    if not subjects:
        print("❌ Лист 'Schedule' порожній або не заповнений.")
        return

    mode = "чергуючийся (А/Б)" if alternating else "звичайний"
    print(f"📚 Знайдено предметів: {len(subjects)}  |  Режим розкладу: {mode}")
    if alternating and not config.WEEK_A_START:
        print("⚠️  WEEK_A_START не вказано в .env — всі дати вважаються тижнем А!")
    for subj, wdays in subjects.items():
        a = ", ".join(DAY_NAMES[d] for d in sorted(wdays["А"])) or "—"
        b = ", ".join(DAY_NAMES[d] for d in sorted(wdays["Б"])) or "—"
        if a == b:
            print(f"  • {subj} ({a})")
        else:
            print(f"  • {subj}  А: {a}  |  Б: {b}")
    print()

    for i, (subject, week_days) in enumerate(subjects.items()):
        print(f"Обробляю '{subject}'...")
        for attempt in range(3):
            try:
                ss_fresh = client.open_by_key(config.SPREADSHEET_ID)
                setup_subject_sheet(ss_fresh, subject, week_days, students)
                break
            except Exception as e:
                if attempt < 2:
                    wait = 30 * (attempt + 1)
                    print(f"  ⚠️  {e.__class__.__name__}. Повтор через {wait} сек...")
                    time.sleep(wait)
                else:
                    print(f"  ❌ Не вдалося після 3 спроб: {e}")
        if i < len(subjects) - 1:
            print("  ⏳ Пауза 15 сек (ліміт API)...")
            time.sleep(15)

    print(f"\n🎉 Готово! Оброблено {len(subjects)} предметів.")


if __name__ == "__main__":
    setup()
