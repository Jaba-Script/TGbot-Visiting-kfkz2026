import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import config

SCOPES   = ["https://www.googleapis.com/auth/spreadsheets"]
DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]


def get_client():
    creds = Credentials.from_service_account_file(config.CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def get_spreadsheet():
    return get_client().open_by_key(config.SPREADSHEET_ID)


# ── Розклад ───────────────────────────────────────────────────────────────────

def get_schedule_for_today() -> list[tuple[str, str]]:
    """Повертає [(номер_пари, предмет), ...] для сьогоднішнього дня."""
    day_idx = datetime.now().weekday()
    if day_idx >= 5:
        return []

    sheet = get_spreadsheet().worksheet("Schedule")
    data  = sheet.get_all_values()
    col   = day_idx + 1

    pairs = []
    for row in data[1:]:
        if len(row) > col:
            num  = row[0].strip()
            subj = row[col].strip()
            if num and subj and subj not in ("—", "-", ""):
                pairs.append((num, subj))
    return pairs


# ── Студенти ──────────────────────────────────────────────────────────────────

def get_students() -> list[str]:
    values = get_spreadsheet().worksheet("Студенти").col_values(1)[1:]
    return [s.strip() for s in values if s.strip()]


# ── Log: запис ────────────────────────────────────────────────────────────────

def log_absences(date: str, pair_num: str, subject: str,
                 absent: list[str], marked_by: str) -> None:
    if not absent:
        return
    log   = get_spreadsheet().worksheet("Log")
    ts    = datetime.now().strftime("%H:%M:%S")
    day   = DAY_NAMES[datetime.now().weekday()]
    rows  = [[date, day, pair_num, subject, s, "Відсутній", marked_by, ts]
             for s in absent]
    log.append_rows(rows, value_input_option="USER_ENTERED")


# ── Log: перевірка дублювання ─────────────────────────────────────────────────

def already_marked(date: str, pair_num: str, subject: str) -> bool:
    """True якщо ця пара вже відмічена сьогодні."""
    rows = get_spreadsheet().worksheet("Log").get_all_values()[1:]
    return any(
        len(r) >= 4 and r[0] == date and r[2] == pair_num and r[3] == subject
        for r in rows
    )


# ── Log: останні записи (для /edit і /history) ────────────────────────────────

def get_recent_absences(n: int = 15) -> list[dict]:
    """
    Повертає останні n записів з Log (найновіші першими).
    Кожен запис: {row, date, day, pair, subject, student}
    row — номер рядка в таблиці (1-based), потрібен для видалення.
    """
    all_rows = get_spreadsheet().worksheet("Log").get_all_values()
    data     = all_rows[1:]  # без заголовка
    recent   = data[-n:] if len(data) >= n else data

    result = []
    base   = len(all_rows) - len(recent)   # індекс першого рядка вибірки
    for i, r in enumerate(recent):
        if len(r) >= 5:
            result.append({
                "row":     base + i + 1,   # 1-based номер рядка в Sheet
                "date":    r[0],
                "day":     r[1],
                "pair":    r[2],
                "subject": r[3],
                "student": r[4],
            })
    result.reverse()   # найновіші першими
    return result


def get_recent_pairs(n: int = 5) -> list[dict]:
    """
    Повертає останні n унікальних пар з Log у форматі:
    [{date, pair, subject, students: [...]}, ...]
    """
    all_rows = get_spreadsheet().worksheet("Log").get_all_values()[1:]
    seen, pairs = [], []

    for r in reversed(all_rows):
        if len(r) < 5:
            continue
        key = (r[0], r[2], r[3])   # date, pair, subject
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


# ── Log: видалення рядка ──────────────────────────────────────────────────────

def delete_log_row(row_number: int) -> None:
    """Видаляє рядок з Log за його номером (1-based)."""
    get_spreadsheet().worksheet("Log").delete_rows(row_number)
