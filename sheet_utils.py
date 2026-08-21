"""
Спільні утиліти для setup_summary.py і setup_subjects.py.
"""

SEMESTER_1 = {9, 10, 11, 12}
SEMESTER_2 = {1, 2, 3, 4, 5, 6}

UA_MONTHS = {
    1: "Січень",  2: "Лютий",    3: "Березень", 4: "Квітень",
    5: "Травень", 6: "Червень",  7: "Липень",   8: "Серпень",
    9: "Вересень",10: "Жовтень", 11: "Листопад",12: "Грудень",
}

# Кольори підсумкових стовпців (RGB 0.0–1.0, ненав'язливі відтінки)
COL_COLORS = {
    "month_total":    {"red": 0.788, "green": 0.867, "blue": 1.0},    # блакитний
    "semester_total": {"red": 1.0,   "green": 0.878, "blue": 0.627},  # бурштиновий
    "grand_total":    {"red": 0.714, "green": 0.835, "blue": 0.659},  # зелений
}


def col_letter(n: int) -> str:
    """1→A, 27→AA тощо."""
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def build_columns(dates: list) -> list[dict]:
    """
    Будує список дескрипторів колонок з підсумками по місяцях і семестрах.
    dates — відсортований список дат занять.
    """
    months: dict = {}
    for d in dates:
        months.setdefault((d.year, d.month), []).append(d)

    columns, sem1_cols, sem2_cols = [], [], []
    col_idx = 2  # колонка B = індекс 2

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


def make_formula(col_desc: dict, row: int, subject: str = None) -> str:
    """Формула для клітинки. subject=None → Зведена (всі предмети)."""
    t, c = col_desc["type"], col_letter(col_desc["col"])
    if t == "date":
        base = f"=COUNTIFS(Log!$E:$E;$A{row};Log!$A:$A;{c}$1"
        if subject:
            base += f';Log!$D:$D;"{subject}"'
        return base + ")*2"
    elif t == "month_total":
        cols = col_desc["date_cols"]
        return f"=SUM({col_letter(cols[0])}{row}:{col_letter(cols[-1])}{row})"
    elif t in ("semester_total", "grand_total"):
        key = "month_cols" if t == "semester_total" else "sem_cols"
        parts = "+".join(f"{col_letter(mc)}{row}" for mc in col_desc[key])
        return f"={parts}"
    return ""


def format_sheet(ss, ws, n_students: int, n_cols: int, columns: list):
    """
    Одним batch_update застосовує:
     - приховання нулів (порожньо якщо 0)
     - кольори підсумкових стовпців
     - жирний шрифт підсумкових стовпців
     - автопідбір ширини колонки A (імена студентів)
    """
    sid = ws.id
    requests = []

    # ── Приховати нулі ────────────────────────────────────────────────────────
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 1,
                  "endRowIndex": n_students + 1,
                  "startColumnIndex": 1, "endColumnIndex": n_cols},
        "cell": {"userEnteredFormat": {
            "numberFormat": {"type": "NUMBER", "pattern": '[=0]"";General'}}},
        "fields": "userEnteredFormat.numberFormat",
    }})

    # ── Колір + жирний для підсумкових стовпців ───────────────────────────────
    for col in columns:
        if col["type"] not in COL_COLORS:
            continue
        ci    = col["col"] - 1   # 0-based
        color = COL_COLORS[col["type"]]
        requests.append({"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0,
                      "endRowIndex": n_students + 1,
                      "startColumnIndex": ci, "endColumnIndex": ci + 1},
            "cell": {"userEnteredFormat": {
                "backgroundColor": color,
                "textFormat": {"bold": True},
            }},
            "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.bold",
        }})

    # ── Автопідбір ширини колонки A ───────────────────────────────────────────
    requests.append({"autoResizeDimensions": {
        "dimensions": {"sheetId": sid, "dimension": "COLUMNS",
                       "startIndex": 0, "endIndex": 1}
    }})

    ss.batch_update({"requests": requests})
