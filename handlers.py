import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime

import sheets
import keyboards
from keyboards import edit_keyboard
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
                f"Хочеш перевідмітити? Старі записи будуть видалені і замінені новими.",
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
    await state.update_data(overwrite=True)
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
    overwrite = data.get("overwrite", False)
    try:
        if overwrite:
            sheets.delete_and_relog(data["date"], data["pair_num"],
                                    data["subject"], absent, marked_by)
        else:
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
#  /edit — видалення кількох записів (мультиселект)
# ══════════════════════════════════════════════════════════════════════════════

@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    try:
        absences = sheets.get_recent_absences(20)
    except Exception as e:
        logger.error(f"Помилка /edit: {e}")
        await message.answer("❌ Не вдалося завантажити журнал.")
        return

    if not absences:
        await message.answer("📋 Журнал порожній — нічого видаляти.")
        return

    await state.set_state(EditFlow.select_records)
    await state.update_data(absences=absences, selected=set())

    text = ("🗑 <b>Оберіть записи для видалення</b>" + chr(10) + "<i>Натискай — виділить запис. Підтверди коли готово.</i>")
    await message.answer(
        text,
        reply_markup=edit_keyboard(absences, set()),
        parse_mode="HTML"
    )

@router.callback_query(EditFlow.select_records, F.data.startswith("etoggle:"))
async def edit_toggle(callback: CallbackQuery, state: FSMContext):
    idx  = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = set(data.get("selected", set()))

    selected.discard(idx) if idx in selected else selected.add(idx)
    await state.update_data(selected=selected)

    await callback.message.edit_reply_markup(
        reply_markup=edit_keyboard(data["absences"], selected)
    )
    await callback.answer()


@router.callback_query(EditFlow.select_records, F.data == "econfirm")
async def edit_confirm(callback: CallbackQuery, state: FSMContext):
    data     = await state.get_data()
    absences = data["absences"]
    selected = set(data.get("selected", set()))

    if not selected:
        await callback.answer("⚠️ Нічого не вибрано.", show_alert=True)
        return

    to_delete = [absences[i] for i in selected if i < len(absences)]
    row_nums  = [a["row"] for a in to_delete]

    await callback.message.edit_text("⏳ Видаляю записи...")
    try:
        sheets.delete_log_rows(row_nums)
    except Exception as e:
        logger.error(f"Помилка видалення: {e}")
        await callback.message.edit_text("❌ Не вдалося видалити записи.")
        await state.clear()
        await callback.answer()
        return

    deleted_list = "\n".join(
        f"  • {a['student']} — {a['subject']} ({a['date']})"
        for a in to_delete
    )
    await callback.message.edit_text(
        f"✅ <b>Видалено {len(to_delete)} записів:</b>\n{deleted_list}",
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer()


@router.callback_query(EditFlow.select_records, F.data == "eclose")
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


# ══════════════════════════════════════════════════════════════════════════════
#  /status — перевірка підключення
# ══════════════════════════════════════════════════════════════════════════════

@router.message(Command("status"))
async def cmd_status(message: Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer("⏳ Перевіряю підключення...")
    try:
        info = sheets.check_connection()
    except Exception as e:
        await message.answer(f"❌ Не вдалося підключитись до таблиці:\n<code>{e}</code>",
                             parse_mode="HTML")
        return

    if info["ok"]:
        await message.answer(
            f"✅ <b>Все працює!</b>\n\n"
            f"📊 Листів у таблиці: {len(info['sheets'])}\n"
            f"👥 Студентів: {info['students']}\n"
            f"📋 Листи: {', '.join(info['sheets'][:8])}"
            f"{'...' if len(info['sheets']) > 8 else ''}",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"⚠️ <b>Таблиця доступна, але є проблеми:</b>\n\n"
            f"❌ Відсутні листи: {', '.join(info['missing'])}",
            parse_mode="HTML"
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Catch-all: протухлі кнопки після перезапуску бота
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query()
async def stale_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обробляє будь-який callback який не перехопили інші хендлери.
    Зазвичай це кнопки з повідомлень до перезапуску бота.
    """
    await state.clear()
    await callback.answer(
        "⚠️ Сесія застаріла після перезапуску бота. Почни заново.",
        show_alert=True
    )
