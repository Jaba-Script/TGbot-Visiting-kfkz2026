from aiogram.fsm.state import State, StatesGroup

class AttendanceFlow(StatesGroup):
    select_pair = State()    # вибір пари з розкладу
    mark_students = State()  # відмічання відсутніх
