# handlers/attendance.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from datetime import date

from services import AttendanceService
from repositories import get_available_classes, get_students_by_class, get_session_records, get_session_result, delete_session
from core.keyboards import BTN_START_ROLL, build_menu_keyboard
from core.roles import check_access, Role

attendance_router = Router()


class AttendanceStates(StatesGroup):
    choosing_class = State()
    marking = State()


@attendance_router.message(F.text == BTN_START_ROLL)
async def start_attendance(message: Message, state: FSMContext) -> None:
    if not check_access(message.from_user.id, [Role.SUBJECT_TEACHER, Role.CLASS_TEACHER]):
        await message.answer("У вас нет прав для проведения переклички.")
        return
    available = get_available_classes(date.today())
    if not available:
        await message.answer("Все классы уже заняты на сегодня.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        *[[InlineKeyboardButton(text=c.name, callback_data=f"att:class:{c.id}")] for c in available],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="att:cancel_class")],
    ])
    sent = await message.answer("Выберите класс:", reply_markup=kb)
    await state.update_data(class_msg_id=sent.message_id)
    await state.set_state(AttendanceStates.choosing_class)


# ── Блокировка случайного текста при выборе класса ──
@attendance_router.message(AttendanceStates.choosing_class)
async def text_during_class_choice(message: Message) -> None:
    await message.answer("Пожалуйста, выберите класс из списка кнопок или нажмите «Отмена».")


@attendance_router.callback_query(AttendanceStates.choosing_class, F.data == "att:cancel_class")
async def cancel_class_choice(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.delete()
    await callback.message.answer("Выберите действие:", reply_markup=build_menu_keyboard(callback.from_user.id))
    await state.clear()
    await callback.answer("Отменено")


@attendance_router.callback_query(AttendanceStates.choosing_class, F.data.startswith("att:class:"))
async def class_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    class_id = int(callback.data.split(":")[-1])
    session, result = AttendanceService.start_attendance(callback.from_user.id, class_id)
    if session is None:
        await callback.message.answer(result)
        await callback.answer()
        await state.clear()
        return
    data = await state.get_data()
    await _safe_delete(callback, data.get("class_msg_id"))
    await state.update_data(session_id=session.id, class_id=class_id)
    students = get_students_by_class(class_id)
    kb = _build_marking_keyboard(students, session.id, [])
    sent = await callback.message.answer(
        "Нажмите на ученика, чтобы отметить отсутствующим.\nЗавершите кнопкой «Отправить».",
        reply_markup=kb,
    )
    await state.update_data(marking_msg_id=sent.message_id)
    await state.set_state(AttendanceStates.marking)
    await callback.answer()


# ── Блокировка случайного текста при отметке ──
@attendance_router.message(AttendanceStates.marking)
async def text_during_marking(message: Message) -> None:
    await message.answer("Используйте кнопки для отметки отсутствующих. Завершите кнопкой «Отправить».")


@attendance_router.callback_query(AttendanceStates.marking, F.data.startswith("att:toggle:"))
async def toggle_student(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    session_id = int(parts[2])
    student_id = int(parts[3])
    AttendanceService.toggle_student(session_id, student_id)
    data = await state.get_data()
    students = get_students_by_class(data["class_id"])
    records = get_session_records(session_id)
    kb = _build_marking_keyboard(students, session_id, records)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@attendance_router.callback_query(AttendanceStates.marking, F.data.startswith("att:cancel:"))
async def cancel_marking(callback: CallbackQuery, state: FSMContext) -> None:
    session_id = int(callback.data.split(":")[-1])
    delete_session(session_id)
    data = await state.get_data()
    await _safe_delete(callback, data.get("marking_msg_id"))
    await callback.message.answer("Выберите действие:", reply_markup=build_menu_keyboard(callback.from_user.id))
    await state.clear()
    await callback.answer("Отменено")


@attendance_router.callback_query(AttendanceStates.marking, F.data.startswith("att:submit:"))
async def submit_attendance(callback: CallbackQuery, state: FSMContext) -> None:
    session_id = int(callback.data.split(":")[-1])
    AttendanceService.complete_session(session_id)
    result = get_session_result(session_id)
    if result:
        text = f"✅ Перекличка в классе {result.class_name} завершена."
        if result.absent:
            text += f"\nОтсутствуют: {', '.join(name for name, _ in result.absent)}"
        else:
            text += "\nОтсутствующих нет."
    else:
        text = "✅ Перекличка завершена."
    data = await state.get_data()
    await _safe_delete(callback, data.get("marking_msg_id"))
    await callback.message.answer(text, reply_markup=build_menu_keyboard(callback.from_user.id))
    await state.clear()
    await callback.answer("Готово!")


def _build_marking_keyboard(students, session_id: int, records: list) -> InlineKeyboardMarkup:
    absent_ids = {r.student_id for r in records if not r.is_present}
    buttons = [
        [InlineKeyboardButton(
            text=f"{'❌' if s.id in absent_ids else '✅'} {s.name}",
            callback_data=f"att:toggle:{session_id}:{s.id}",
        )]
        for s in students
    ]
    buttons.append([
        InlineKeyboardButton(text="✅ Отправить", callback_data=f"att:submit:{session_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"att:cancel:{session_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _safe_delete(callback: CallbackQuery, message_id: int | None) -> None:
    if message_id:
        try:
            await callback.bot.delete_message(callback.message.chat.id, message_id)
        except Exception:
            pass