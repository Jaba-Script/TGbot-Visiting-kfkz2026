from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def pairs_keyboard(pairs: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """Кнопки для вибору пари. pairs = [(номер, предмет), ...]"""
    buttons = [
        [InlineKeyboardButton(
            text=f"📖 Пара {num} — {subject}",
            callback_data=f"pair:{num}:{subject}"
        )]
        for num, subject in pairs
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def students_keyboard(
    students: list[str], absent: set[str]
) -> InlineKeyboardMarkup:
    """
    Кнопки студентів з перемикачем ✅/❌.
    ✅ — присутній (за замовчуванням)
    ❌ — відсутній (відмічений)
    """
    buttons = [
        [InlineKeyboardButton(
            text=f"{'❌' if s in absent else '✅'} {s}",
            callback_data=f"student:{s}"
        )]
        for s in students
    ]

    # Лічильник відсутніх у кнопці підтвердження
    absent_count = len(absent)
    confirm_text = (
        f"✔️ Підтвердити — відсутніх: {absent_count}"
        if absent_count > 0
        else "✔️ Підтвердити — всі присутні"
    )
    buttons.append([InlineKeyboardButton(
        text=confirm_text,
        callback_data="confirm"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def edit_keyboard(absences: list[dict], selected: set[int]) -> InlineKeyboardMarkup:
    """
    Чеклист для /edit. 
    selected — множина індексів вибраних для видалення записів.
    ✅ — буде видалено, ❌ — залишити.
    """
    buttons = []
    for i, a in enumerate(absences):
        mark = "🗑 ✅" if i in selected else "· ❌"
        text = f"{mark} {a['student']} — {a['subject']} ({a['date']})"
        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"etoggle:{i}"
        )])

    count = len(selected)
    confirm_text = (
        f"🗑 Видалити вибрані ({count})" if count > 0 else "· Нічого не вибрано"
    )
    buttons.append([
        InlineKeyboardButton(text=confirm_text, callback_data="econfirm"),
        InlineKeyboardButton(text="✖ Закрити",  callback_data="eclose"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
