import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime

import sheets
import keyboards
from states import AttendanceFlow
import config

logger = logging.getLogger(__name__)
router = Router()

UA_DAYS = ["понеділок", "вівторок", "середу", "четвер", "п'ятницю", "суботу", "неділю"]


def is_allowed(user_id: int) -> bool:
    return user_id in config.ALLOWED_USERS


# ─── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ У вас немає доступу до цього бота.")
        return

    await message.answer(
        "👋 Вітаю! Це бот для відмічання відвідуваності групи.\n\n"
        "📋 <b>Команди:</b>\n"
        "/mark — відмітити відсутніх на парі\n"
        "/cancel — скасувати поточну дію",
        parse_mode="HTML"
    )


# ─── /відмітити ────────────────────────────────────────────────────────────────

@router.message(Command("mark"))
async def cmd_mark(message: Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ У вас немає доступу до цього бота.")
        return

    await message.answer("⏳ Завантажую розклад...")

    try:
        pairs = sheets.get_schedule_for_today()
    except Exception as e:
        logger.error(f"Помилка читання розкладу: {e}")
        await message.answer("❌ Не вдалося завантажити розклад. Перевірте підключення до таблиці.")
        return

    day_idx = datetime.now().weekday()
    if day_idx >= 5:
        await message.answer("📅 Сьогодні вихідний, пар немає.")
        return

    if not pairs:
        await message.answer(f"📅 На {UA_DAYS[day_idx]} пар у розкладі немає.")
        return

    today = datetime.now().strftime("%d.%m.%Y")
    await state.set_state(AttendanceFlow.select_pair)
    await state.update_data(date=today)

    await message.answer(
        f"📅 <b>{today}</b> ({UA_DAYS[day_idx]})\nОберіть пару:",
        reply_markup=keyboards.pairs_keyboard(pairs),
        parse_mode="HTML"
    )


# ─── Вибір пари ────────────────────────────────────────────────────────────────

@router.callback_query(AttendanceFlow.select_pair, F.data.startswith("pair:"))
async def select_pair(callback: CallbackQuery, state: FSMContext):
    _, pair_num, subject = callback.data.split(":", 2)

    try:
        students = sheets.get_students()
    except Exception as e:
        logger.error(f"Помилка читання студентів: {e}")
        await callback.answer("❌ Не вдалося завантажити список студентів.", show_alert=True)
        return

    if not students:
        await callback.answer("❌ Список студентів порожній. Перевірте лист 'Студенти'.", show_alert=True)
        return

    await state.set_state(AttendanceFlow.mark_students)
    await state.update_data(
        pair_num=pair_num,
        subject=subject,
        students=students,
        absent=[],
    )

    data = await state.get_data()
    await callback.message.edit_text(
        f"📚 <b>Пара {pair_num} — {subject}</b>\n"
        f"📅 {data['date']}\n\n"
        f"Натискайте на студентів, щоб відмітити відсутніх:\n"
        f"✅ — присутній  |  ❌ — відсутній",
        reply_markup=keyboards.students_keyboard(students, set()),
        parse_mode="HTML"
    )
    await callback.answer()


# ─── Перемикання студента ──────────────────────────────────────────────────────

@router.callback_query(AttendanceFlow.mark_students, F.data.startswith("student:"))
async def toggle_student(callback: CallbackQuery, state: FSMContext):
    student = callback.data.split(":", 1)[1]
    data = await state.get_data()

    absent = set(data.get("absent", []))
    if student in absent:
        absent.discard(student)
    else:
        absent.add(student)

    await state.update_data(absent=list(absent))

    await callback.message.edit_reply_markup(
        reply_markup=keyboards.students_keyboard(data["students"], absent)
    )
    await callback.answer()


# ─── Підтвердження ─────────────────────────────────────────────────────────────

@router.callback_query(AttendanceFlow.mark_students, F.data == "confirm")
async def confirm_attendance(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    date = data["date"]
    pair_num = data["pair_num"]
    subject = data["subject"]
    absent = data.get("absent", [])
    marked_by = callback.from_user.full_name

    await callback.message.edit_text("⏳ Зберігаю дані в таблицю...")

    try:
        sheets.log_absences(date, pair_num, subject, absent, marked_by)
    except Exception as e:
        logger.error(f"Помилка запису в Log: {e}")
        await callback.message.edit_text(
            "❌ Не вдалося зберегти дані. Спробуйте ще раз або перевірте доступ до таблиці."
        )
        await state.clear()
        await callback.answer()
        return

    if absent:
        absent_list = "\n".join(f"  • {s}" for s in sorted(absent))
        text = (
            f"✅ <b>Збережено!</b>\n\n"
            f"📚 Пара {pair_num} — {subject}\n"
            f"📅 {date}\n\n"
            f"❌ <b>Відсутні ({len(absent)}):</b>\n{absent_list}"
        )
    else:
        text = (
            f"✅ <b>Збережено!</b>\n\n"
            f"📚 Пара {pair_num} — {subject}\n"
            f"📅 {date}\n\n"
            f"🎉 Всі студенти присутні!"
        )

    await callback.message.edit_text(text, parse_mode="HTML")
    await state.clear()
    await callback.answer()


# ─── /скасувати ────────────────────────────────────────────────────────────────

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    current = await state.get_state()
    if current:
        await state.clear()
        await message.answer("❌ Дію скасовано.")
    else:
        await message.answer("Немає активної дії для скасування.")
