import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime

import sheets
import keyboards
from states import AttendanceFlow, EditFlow
import config

logger   = logging.getLogger(__name__)
router   = Router()
UA_DAYS  = ["понеділок","вівторок","середу","четвер","п'ятницю","суботу","неділю"]


def is_allowed(uid: int) -> bool:
    return uid in config.ALLOWED_USERS


# ══════════════════════════════════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════════════════════════════════

@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ У вас немає доступу до цього бота.")
        return
    await message.answer(
        "👋 Вітаю! Це бот для відмічання відвідуваності групи.\n\n"
        "📋 <b>Команди:</b>\n"
        "/mark — відмітити відсутніх на парі\n"
        "/history — переглянути останні пари\n"
        "/edit — виправити помилкову відмітку\n"
        "/cancel — скасувати поточну дію",
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  /mark — відмічання присутності
# ══════════════════════════════════════════════════════════════════════════════

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
        await message.answer("❌ Не вдалося завантажити розклад.")
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


@router.callback_query(AttendanceFlow.select_pair, F.data.startswith("pair:"))
async def select_pair(callback: CallbackQuery, state: FSMContext):
    _, pair_num, subject = callback.data.split(":", 2)

    # ── Перевірка на дублювання ───────────────────────────────────────────────
    data  = await state.get_data()
    today = data["date"]
    try:
        if sheets.already_marked(today, pair_num, subject):
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✏️ Так, перевідмітити", callback_data=f"force:{pair_num}:{subject}"),
                InlineKeyboardButton(text="❌ Скасувати",           callback_data="cancel_mark"),
            ]])
            await callback.message.edit_text(
                f"⚠️ Пара {pair_num} — <b>{subject}</b> на {today} вже відмічена!\n\n"
                f"Хочеш відмітити заново? Нові записи додадуться до існуючих.",
                reply_markup=kb, parse_mode="HTML"
            )
            await callback.answer()
            return
    except Exception as e:
        logger.error(f"Помилка перевірки дублювання: {e}")

    await _load_students(callback, state, pair_num, subject)


@router.callback_query(AttendanceFlow.select_pair, F.data.startswith("force:"))
async def force_mark(callback: CallbackQuery, state: FSMContext):
    _, pair_num, subject = callback.data.split(":", 2)
    await _load_students(callback, state, pair_num, subject)


async def _load_students(callback: CallbackQuery, state: FSMContext,
                         pair_num: str, subject: str):
    try:
        students = sheets.get_students()
    except Exception as e:
        logger.error(f"Помилка читання студентів: {e}")
        await callback.answer("❌ Не вдалося завантажити список студентів.", show_alert=True)
        return
    if not students:
        await callback.answer("❌ Список 'Студенти' порожній.", show_alert=True)
        return

    data = await state.get_data()
    await state.set_state(AttendanceFlow.mark_students)
    await state.update_data(pair_num=pair_num, subject=subject,
                            students=students, absent=[])
    await callback.message.edit_text(
        f"📚 <b>Пара {pair_num} — {subject}</b>\n"
        f"📅 {data['date']}\n\n"
        f"Натискайте на відсутніх:\n✅ — присутній  |  ❌ — відсутній",
        reply_markup=keyboards.students_keyboard(students, set()),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(AttendanceFlow.mark_students, F.data.startswith("student:"))
async def toggle_student(callback: CallbackQuery, state: FSMContext):
    student = callback.data.split(":", 1)[1]
    data    = await state.get_data()
    absent  = set(data.get("absent", []))
    absent.discard(student) if student in absent else absent.add(student)
    await state.update_data(absent=list(absent))
    await callback.message.edit_reply_markup(
        reply_markup=keyboards.students_keyboard(data["students"], absent)
    )
    await callback.answer()


@router.callback_query(AttendanceFlow.mark_students, F.data == "confirm")
async def confirm_attendance(callback: CallbackQuery, state: FSMContext):
    data      = await state.get_data()
    absent    = data.get("absent", [])
    marked_by = callback.from_user.full_name

    await callback.message.edit_text("⏳ Зберігаю дані...")
    try:
        sheets.log_absences(data["date"], data["pair_num"],
                            data["subject"], absent, marked_by)
    except Exception as e:
        logger.error(f"Помилка запису в Log: {e}")
        await callback.message.edit_text("❌ Не вдалося зберегти. Спробуй ще раз.")
        await state.clear()
        await callback.answer()
        return

    if absent:
        lst  = "\n".join(f"  • {s}" for s in sorted(absent))
        text = (f"✅ <b>Збережено!</b>\n\n"
                f"📚 Пара {data['pair_num']} — {data['subject']}\n"
                f"📅 {data['date']}\n\n"
                f"❌ <b>Відсутні ({len(absent)}):</b>\n{lst}")
    else:
        text = (f"✅ <b>Збережено!</b>\n\n"
                f"📚 Пара {data['pair_num']} — {data['subject']}\n"
                f"📅 {data['date']}\n\n🎉 Всі присутні!")

    await callback.message.edit_text(text, parse_mode="HTML")
    await state.clear()
    await callback.answer()


@router.callback_query(AttendanceFlow.select_pair, F.data == "cancel_mark")
async def cancel_mark_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Відмічання скасовано.")
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  /history — останні пари
# ══════════════════════════════════════════════════════════════════════════════

@router.message(Command("history"))
async def cmd_history(message: Message):
    if not is_allowed(message.from_user.id):
        return
    try:
        pairs = sheets.get_recent_pairs(5)
    except Exception as e:
        logger.error(f"Помилка /history: {e}")
        await message.answer("❌ Не вдалося завантажити дані.")
        return

    if not pairs:
        await message.answer("📋 Поки немає записів у журналі.")
        return

    lines = ["📋 <b>Останні 5 пар:</b>\n"]
    for p in pairs:
        lines.append(f"📚 <b>{p['subject']}</b> | Пара {p['pair']} | {p['date']}")
        if p["students"]:
            for s in p["students"]:
                lines.append(f"  ❌ {s}")
        else:
            lines.append("  🎉 Всі були присутні")
        lines.append("")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
#  /edit — виправлення помилки
# ══════════════════════════════════════════════════════════════════════════════

@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    try:
        absences = sheets.get_recent_absences(15)
    except Exception as e:
        logger.error(f"Помилка /edit: {e}")
        await message.answer("❌ Не вдалося завантажити журнал.")
        return

    if not absences:
        await message.answer("📋 Журнал порожній — нічого видаляти.")
        return

    await state.set_state(EditFlow.select_record)
    await state.update_data(absences=absences)

    buttons = [
        [InlineKeyboardButton(
            text=f"❌ {a['student']} — {a['subject']} ({a['date']})",
            callback_data=f"del:{i}"
        )]
        for i, a in enumerate(absences)
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Закрити", callback_data="edit_close")])

    await message.answer(
        "🗑 Оберіть запис для видалення\n"
        "<i>(показано 15 найновіших)</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(EditFlow.select_record, F.data.startswith("del:"))
async def edit_select(callback: CallbackQuery, state: FSMContext):
    idx      = int(callback.data.split(":")[1])
    data     = await state.get_data()
    absences = data["absences"]

    if idx >= len(absences):
        await callback.answer("❌ Запис не знайдено.", show_alert=True)
        return

    a = absences[idx]
    await state.update_data(selected_idx=idx)
    await state.set_state(EditFlow.confirm_delete)

    await callback.message.edit_text(
        f"⚠️ <b>Видалити запис?</b>\n\n"
        f"👤 {a['student']}\n"
        f"📚 {a['subject']} | Пара {a['pair']}\n"
        f"📅 {a['date']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Так, видалити", callback_data="edit_confirm"),
            InlineKeyboardButton(text="← Назад",          callback_data="edit_back"),
        ]]),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(EditFlow.confirm_delete, F.data == "edit_confirm")
async def edit_confirm(callback: CallbackQuery, state: FSMContext):
    data     = await state.get_data()
    a        = data["absences"][data["selected_idx"]]
    try:
        sheets.delete_log_row(a["row"])
    except Exception as e:
        logger.error(f"Помилка видалення рядка: {e}")
        await callback.message.edit_text("❌ Не вдалося видалити запис.")
        await state.clear()
        await callback.answer()
        return

    await callback.message.edit_text(
        f"✅ <b>Запис видалено.</b>\n\n"
        f"👤 {a['student']}\n"
        f"📚 {a['subject']} | Пара {a['pair']}\n"
        f"📅 {a['date']}",
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer()


@router.callback_query(EditFlow.confirm_delete, F.data == "edit_back")
async def edit_back(callback: CallbackQuery, state: FSMContext):
    """Повернутись до списку записів."""
    data     = await state.get_data()
    absences = data["absences"]
    await state.set_state(EditFlow.select_record)

    buttons = [
        [InlineKeyboardButton(
            text=f"❌ {a['student']} — {a['subject']} ({a['date']})",
            callback_data=f"del:{i}"
        )]
        for i, a in enumerate(absences)
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Закрити", callback_data="edit_close")])
    await callback.message.edit_text(
        "🗑 Оберіть запис для видалення\n<i>(показано 15 найновіших)</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "edit_close")
async def edit_close(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("📋 Редагування закрито.")
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  /cancel
# ══════════════════════════════════════════════════════════════════════════════

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    if await state.get_state():
        await state.clear()
        await message.answer("❌ Дію скасовано.")
    else:
        await message.answer("Немає активної дії для скасування.")
