import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import config
from retry import with_retry

SCOPES    = ["https://www.googleapis.com/auth/spreadsheets"]
DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]


def get_client():
    creds = Credentials.from_service_account_file(config.CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def get_spreadsheet():
    return get_client().open_by_key(config.SPREADSHEET_ID)


# ── Тиждень А/Б ───────────────────────────────────────────────────────────────

def get_week_type(target_date=None) -> str | None:
    if not config.WEEK_A_START:
        return None
    if target_date is None:
        target_date = datetime.now().date()
    weeks_since = (target_date - config.WEEK_A_START).days // 7
    return "А" if weeks_since % 2 == 0 else "Б"


# ── Розклад ───────────────────────────────────────────────────────────────────

@with_retry()
def get_schedule_for_today() -> list[tuple[str, str]]:
    day_idx = datetime.now().weekday()
    if day_idx >= 5:
        return []

    data = get_spreadsheet().worksheet("Schedule").get_all_values()
    if not data:
        return []

    alternating = data[0][0].strip() == "Тиждень"

    if alternating:
        week_type = get_week_type()
        col = day_idx + 2
        pairs = []
        for row in data[1:]:
            if len(row) <= col:
                continue
            if week_type and row[0].strip() != week_type:
                continue
            num, subj = row[1].strip(), row[col].strip()
            if num and subj and subj not in ("—", "-", ""):
                pairs.append((num, subj))
    else:
        col = day_idx + 1
        pairs = []
        for row in data[1:]:
            if len(row) <= col:
                continue
            num, subj = row[0].strip(), row[col].strip()
            if num and subj and subj not in ("—", "-", ""):
                pairs.append((num, subj))

    return pairs


# ── Студенти ──────────────────────────────────────────────────────────────────

@with_retry()
def get_students() -> list[str]:
    values = get_spreadsheet().worksheet("Студенти").col_values(1)[1:]
    return [s.strip() for s in values if s.strip()]


# ── Log: запис ────────────────────────────────────────────────────────────────

@with_retry()
def log_absences(date: str, pair_num: str, subject: str,
                 absent: list[str], marked_by: str) -> None:
    if not absent:
        return
    log  = get_spreadsheet().worksheet("Log")
    ts   = datetime.now().strftime("%H:%M:%S")
    day  = DAY_NAMES[datetime.now().weekday()]
    rows = [[date, day, pair_num, subject, s, "Відсутній", marked_by, ts]
            for s in absent]
    log.append_rows(rows, value_input_option="USER_ENTERED")


# ── Log: перевірка дублювання ─────────────────────────────────────────────────

@with_retry()
def already_marked(date: str, pair_num: str, subject: str) -> bool:
    rows = get_spreadsheet().worksheet("Log").get_all_values()[1:]
    return any(
        len(r) >= 4 and r[0] == date and r[2] == pair_num and r[3] == subject
        for r in rows
    )


# ── Log: останні записи ───────────────────────────────────────────────────────

@with_retry()
def get_recent_absences(n: int = 15) -> list[dict]:
    all_rows = get_spreadsheet().worksheet("Log").get_all_values()
    data     = all_rows[1:]
    recent   = data[-n:] if len(data) >= n else data
    base     = len(all_rows) - len(recent)
    result   = []
    for i, r in enumerate(recent):
        if len(r) >= 5:
            result.append({
                "row": base + i + 1,
                "date": r[0], "day": r[1], "pair": r[2],
                "subject": r[3], "student": r[4],
            })
    result.reverse()
    return result


@with_retry()
def get_recent_pairs(n: int = 5) -> list[dict]:
    all_rows = get_spreadsheet().worksheet("Log").get_all_values()[1:]
    seen, pairs = [], []
    for r in reversed(all_rows):
        if len(r) < 5:
            continue
        key = (r[0], r[2], r[3])
        if key not in seen:
            seen.append(key)
            pairs.append({"date": r[0], "pair": r[2], "subject": r[3], "students": []})
        for p in pairs:
            if (p["date"], p["pair"], p["subject"]) == key:
                p["students"].append(r[4])
                break
        if len(pairs) == n:
            break
    return pairs


# ── Log: видалення ────────────────────────────────────────────────────────────

@with_retry()
def delete_log_row(row_number: int) -> None:
    get_spreadsheet().worksheet("Log").delete_rows(row_number)


# ── Статус підключення ────────────────────────────────────────────────────────

@with_retry(max_attempts=1)
def check_connection() -> dict:
    """Перевіряє підключення до таблиці. Повертає {ok, sheets, students}."""
    ss      = get_spreadsheet()
    titles  = [ws.title for ws in ss.worksheets()]
    required = {"Schedule", "Log", "Студенти"}
    missing  = required - set(titles)
    students = ss.worksheet("Студенти").col_values(1)[1:] if not missing else []
    return {
        "ok":       len(missing) == 0,
        "sheets":   titles,
        "missing":  list(missing),
        "students": len([s for s in students if s.strip()]),
    }


def delete_log_rows(row_numbers: list[int]) -> None:
    """
    Видаляє кілька рядків з Log за їх номерами (1-based).
    Видаляє з кінця щоб уникнути зміщення індексів.
    """
    if not row_numbers:
        return
    ws = get_spreadsheet().worksheet("Log")
    for row_num in sorted(row_numbers, reverse=True):
        ws.delete_rows(row_num)


@with_retry()
def delete_and_relog(date: str, pair_num: str, subject: str,
                     absent: list[str], marked_by: str) -> None:
    """
    Видаляє всі існуючі записи пари з Log і записує нові.
    Використовується при переотмічанні вже відміченої пари.
    """
    ss  = get_spreadsheet()
    log = ss.worksheet("Log")

    # Знаходимо всі рядки цієї пари (від кінця щоб не зміщувались індекси)
    all_rows = log.get_all_values()
    to_delete = [
        i + 1  # 1-based індекс рядка в таблиці (рядок 1 = заголовок)
        for i, r in enumerate(all_rows)
        if len(r) >= 4 and r[0] == date and r[2] == pair_num and r[3] == subject
    ]
    for row_num in sorted(to_delete, reverse=True):
        log.delete_rows(row_num)

    # Записуємо нові
    if absent:
        ts   = datetime.now().strftime("%H:%M:%S")
        day  = DAY_NAMES[datetime.now().weekday()]
        rows = [[date, day, pair_num, subject, s, "Відсутній", marked_by, ts]
                for s in absent]
        log.append_rows(rows, value_input_option="USER_ENTERED")
