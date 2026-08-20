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
