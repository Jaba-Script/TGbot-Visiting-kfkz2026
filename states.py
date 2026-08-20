from aiogram.fsm.state import State, StatesGroup


class AttendanceFlow(StatesGroup):
    select_pair    = State()   # вибір пари з розкладу
    mark_students  = State()   # відмічання відсутніх


class EditFlow(StatesGroup):
    select_record  = State()   # вибір запису для видалення
    confirm_delete = State()   # підтвердження видалення
