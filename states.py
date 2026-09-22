from aiogram.fsm.state import State, StatesGroup


class AttendanceFlow(StatesGroup):
    select_pair   = State()
    mark_students = State()


class EditFlow(StatesGroup):
    select_records = State()  # мультиселект записів для видалення
