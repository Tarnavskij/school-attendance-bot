# handlers/attendance.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from datetime import date

from services import AttendanceService
from repositories import (
    get_available_classes, get_students_by_class,
    get_session_records, get_session_result, delete_session,
    get_teacher_by_telegram_id,
)
from core.keyboards import BTN_START_ROLL, build_menu_keyboard
from core.roles import check_access, Role
from helpers.session_card import get_today_session_card

attendance_router = Router()


class AttendanceStates(StatesGroup):
    choosing_class = State()
    marking = State()


@attendance_router.message(F.text == BTN_START_ROLL)
async def start_attendance(message: Message, state: FSMContext) -> None:
    if not check_access(message.from_user.id, [Role.SUBJECT_TEACHER, Role.CLASS_TEACHER]):
        await message.answer("У вас нет прав для проведения переклички.")
        return

    card = get_today_session_card(message.from_user.id)
    if card:
        await message.answer(card)
        return

    available = get_available_classes(date.today())
    if not available:
        await message.answer("Все классы уже отмечены на сегодня.")
        return

    kb = _build_class_keyboard(available)
    sent = await message.answer("🏫 Выберите класс для переклички:", reply_markup=kb)
    await state.update_data(flow_msg_id=sent.message_id, chat_id=sent.chat.id)
    await state.set_state(AttendanceStates.choosing_class)


def _build_class_keyboard(available_classes) -> InlineKeyboardMarkup:
    """Строит сетку из кнопок классов (по 2 в ряд) + кнопка Отмена."""
    buttons = []
    for c in available_classes:
        buttons.append(InlineKeyboardButton(text=c.name, callback_data=f"att:class:{c.id}"))
    # Разбиваем на ряды по 2 кнопки
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="att:cancel_flow")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Блокировка случайного текста при выборе класса ──
@attendance_router.message(AttendanceStates.choosing_class)
async def text_during_class_choice(message: Message) -> None:
    await message.delete()


@attendance_router.callback_query(AttendanceStates.choosing_class, F.data == "att:cancel_flow")
async def cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text("Перекличка отменена.")
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=build_menu_keyboard(callback.from_user.id),
    )
    await state.clear()
    await callback.answer()


@attendance_router.callback_query(AttendanceStates.choosing_class, F.data.startswith("att:class:"))
async def class_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    class_id = int(callback.data.split(":")[-1])
    session, result = AttendanceService.start_attendance(callback.from_user.id, class_id)

    if session is None:
        await callback.message.edit_text(result)
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=build_menu_keyboard(callback.from_user.id),
        )
        await state.clear()
        await callback.answer()
        return

    await state.update_data(session_id=session.id, class_id=class_id)
    students = get_students_by_class(class_id)
    kb = _build_marking_keyboard(students, session.id, [])

    await callback.message.edit_text(
        "✅ — присутствует   ❌ — отсутствует\n\nНажмите на ученика, чтобы изменить статус:",
        reply_markup=kb,
    )
    await state.set_state(AttendanceStates.marking)
    await callback.answer()


# ── Блокировка случайного текста при отметке ──
@attendance_router.message(AttendanceStates.marking)
async def text_during_marking(message: Message) -> None:
    await message.delete()


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
    await callback.message.edit_text("Перекличка отменена.")
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=build_menu_keyboard(callback.from_user.id),
    )
    await state.clear()
    await callback.answer()


@attendance_router.callback_query(AttendanceStates.marking, F.data.startswith("att:submit:"))
async def submit_attendance(callback: CallbackQuery, state: FSMContext) -> None:
    session_id = int(callback.data.split(":")[-1])
    AttendanceService.complete_session(session_id)
    result = get_session_result(session_id)

    if result:
        lines = [f"📋 Ваша перекличка сегодня — класс {result.class_name}"]
        if result.absent:
            lines.append(f"\nОтсутствуют ({len(result.absent)}):")
            for name, reason in result.absent:
                reason_str = f" — {reason}" if reason else ""
                lines.append(f"  • {name}{reason_str}")
        else:
            lines.append("\n✅ Все присутствовали")
        card_text = "\n".join(lines)
    else:
        card_text = "✅ Перекличка завершена."

    await callback.message.edit_text(card_text, reply_markup=None)
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=build_menu_keyboard(callback.from_user.id),
    )
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