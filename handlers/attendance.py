# handlers/attendance.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from datetime import date

from services import AttendanceService
from repositories import (
    get_available_classes,
    get_students_by_class,
    get_session_records,
    get_session_result,
    delete_session,
    get_teacher_by_telegram_id,
    get_teacher_session_today,
    get_class_teacher_for_class,
    get_default_school_id,
    update_session_records,
)
from core.keyboards import BTN_START_ROLL, build_menu_keyboard
from core.roles import check_access, Role, is_admin
from core.school_context import get_school_id_for_admin
from helpers.session_card import get_today_session_card_data

attendance_router = Router()


class AttendanceStates(StatesGroup):
    choosing_class = State()
    marking = State()
    editing_own = State()


@attendance_router.message(F.text == BTN_START_ROLL)
async def start_attendance(message: Message, state: FSMContext) -> None:
    if not check_access(message.from_user.id, [Role.SUBJECT_TEACHER, Role.CLASS_TEACHER]):
        await message.answer("У вас нет прав для проведения переклички.")
        return

    teacher = get_teacher_by_telegram_id(message.from_user.id)
    if not teacher:
        await message.answer("Вы не зарегистрированы.")
        return

    # Администратору не показываем карточку
    if not is_admin(message.from_user.id):
        card_data = get_today_session_card_data(message.from_user.id)
        if card_data:
            kb = None
            if card_data["status"] == "completed":
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="✏️ Исправить",
                        callback_data=f"att:edit_own:{card_data['session_id']}",
                    )],
                    [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")],
                ])
            await message.answer(card_data["text"], reply_markup=kb)
            return

    # Определяем школу
    if is_admin(message.from_user.id):
        school_id = get_school_id_for_admin(message.from_user.id)
    else:
        school_id = teacher.school_id

    available = get_available_classes(date.today(), school_id=school_id)
    if not available:
        await message.answer("Все классы уже отмечены на сегодня.")
        return

    kb = _build_class_keyboard(available)
    sent = await message.answer("🏫 Выберите класс для переклички:", reply_markup=kb)
    await state.update_data(flow_msg_id=sent.message_id, chat_id=sent.chat.id)
    await state.set_state(AttendanceStates.choosing_class)


def _build_class_keyboard(available_classes) -> InlineKeyboardMarkup:
    groups: dict[int, list] = {}
    for c in available_classes:
        grade = c.grade or 0
        groups.setdefault(grade, []).append(c)

    rows = []
    for grade in sorted(groups.keys()):
        buttons = []
        for c in groups[grade]:
            buttons.append(InlineKeyboardButton(
                text=c.name,
                callback_data=f"att:class:{c.id}:{c.school_id}"
            ))
        rows.append(buttons)

    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="att:cancel_flow")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    _, _, class_id_str, school_id_str = callback.data.split(":")
    class_id = int(class_id_str)
    callback_school_id = int(school_id_str)  # присланное значение — НЕ доверяем ему напрямую

    teacher = get_teacher_by_telegram_id(callback.from_user.id)
    if is_admin(callback.from_user.id):
        real_school_id = get_school_id_for_admin(callback.from_user.id)
    elif teacher:
        real_school_id = teacher.school_id
    else:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return

    if callback_school_id != real_school_id:
        await callback.answer("Недопустимая школа.", show_alert=True)
        return

    school_id = real_school_id

    session, result = AttendanceService.start_attendance(
        callback.from_user.id, class_id,
        teacher_school_id=school_id,
    )

    if session is None:
        await callback.message.edit_text(result)
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=build_menu_keyboard(callback.from_user.id),
        )
        await state.clear()
        await callback.answer()
        return

    await state.update_data(session_id=session.id, class_id=class_id, school_id=school_id)
    students = get_students_by_class(class_id, school_id=school_id)
    kb = _build_marking_keyboard(students, session.id, [])

    await callback.message.edit_text(
        "✅ — присутствует   ❌ — отсутствует\n\nНажмите на ученика, чтобы изменить статус:",
        reply_markup=kb,
    )
    await state.set_state(AttendanceStates.marking)
    await callback.answer()


@attendance_router.message(AttendanceStates.marking)
async def text_during_marking(message: Message) -> None:
    await message.delete()


@attendance_router.callback_query(AttendanceStates.marking, F.data.startswith("att:toggle:"))
async def toggle_student(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    session_id = int(parts[2])
    student_id = int(parts[3])

    data = await state.get_data()
    expected_session_id = data.get("session_id")
    if expected_session_id is None or session_id != expected_session_id:
        await callback.answer("Сессия недействительна.", show_alert=True)
        return

    AttendanceService.toggle_student(session_id, student_id)
    school_id = data.get("school_id")
    students = get_students_by_class(data["class_id"], school_id=school_id)
    records = get_session_records(session_id)
    kb = _build_marking_keyboard(students, session_id, records)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@attendance_router.callback_query(AttendanceStates.marking, F.data.startswith("att:cancel:"))
async def cancel_marking(callback: CallbackQuery, state: FSMContext) -> None:
    session_id = int(callback.data.split(":")[-1])

    data = await state.get_data()
    expected_session_id = data.get("session_id")
    if expected_session_id is None or session_id != expected_session_id:
        await callback.answer("Сессия недействительна.", show_alert=True)
        return

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

    data_check = await state.get_data()
    expected_session_id = data_check.get("session_id")
    if expected_session_id is None or session_id != expected_session_id:
        await callback.answer("Сессия недействительна.", show_alert=True)
        return

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

        # --- Уведомление классного руководителя ---
        # Получаем school_id из состояния
        data = await state.get_data()
        school_id = data.get("school_id")
        if not school_id:
            # fallback: получаем ID первой школы
            school_id = get_default_school_id()  # <-- заменили

        class_teacher = get_class_teacher_for_class(result.class_id, school_id)
        if class_teacher and class_teacher.telegram_id != callback.from_user.id:
            notify_lines = [f"📋 Перекличка в вашем классе {result.class_name} завершена."]
            if result.absent:
                notify_lines.append(f"\nОтсутствуют ({len(result.absent)}):")
                for name, reason in result.absent:
                    reason_str = f" — {reason}" if reason else ""
                    notify_lines.append(f"  • {name}{reason_str}")
            else:
                notify_lines.append("\n✅ Все присутствовали")
            try:
                await callback.bot.send_message(class_teacher.telegram_id, "\n".join(notify_lines))
            except Exception:
                pass
    else:
        card_text = "✅ Перекличка завершена."

    notify = getattr(callback.bot, "notify_web", None)
    if notify:
        await notify("summary_update")

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


# ── Редактирование своей переклички (для учителя, который её провёл) ─────────

@attendance_router.callback_query(F.data.startswith("att:edit_own:"))
async def edit_own_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not check_access(callback.from_user.id, [Role.SUBJECT_TEACHER, Role.CLASS_TEACHER]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    session_id = int(callback.data.split(":")[-1])

    teacher = get_teacher_by_telegram_id(callback.from_user.id)
    if not teacher:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return

    # Убеждаемся, что это действительно сессия этого учителя за сегодня
    session = get_teacher_session_today(teacher.id, date.today(), school_id=teacher.school_id)
    if not session or session.id != session_id:
        await callback.answer("Сессия не найдена.", show_alert=True)
        return

    if session.status != "completed":
        await callback.answer("Эту перекличку уже нельзя редактировать.", show_alert=True)
        return

    students = get_students_by_class(session.class_id, school_id=teacher.school_id)
    records = get_session_records(session_id)
    records_map = {r.student_id: r for r in records}

    items: dict[int, dict] = {}
    for s in students:
        rec = records_map.get(s.id)
        if rec:
            items[s.id] = {
                "name": s.name,
                "is_present": rec.is_present,
                "reason": rec.reason,
            }
        else:
            # Ученик добавлен после переклички — по умолчанию присутствует
            items[s.id] = {"name": s.name, "is_present": True, "reason": None}

    # Сохраняем исходное состояние отметок — нужно для вычисления diff при сохранении
    original_state = {sid: it["is_present"] for sid, it in items.items()}

    await state.update_data(
        session_id=session_id,
        class_id=session.class_id,
        school_id=teacher.school_id,
        class_name=session.class_name,
        items=items,
        original_state=original_state,
    )
    await state.set_state(AttendanceStates.editing_own)

    await _render_edit_own_keyboard(callback, state)
    await callback.answer()


@attendance_router.callback_query(AttendanceStates.editing_own, F.data.startswith("att:edit_toggle:"))
async def edit_own_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    student_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    items = data.get("items", {})
    if student_id in items:
        items[student_id]["is_present"] = not items[student_id]["is_present"]
        await state.update_data(items=items)
    await _render_edit_own_keyboard(callback, state)
    await callback.answer()


@attendance_router.callback_query(AttendanceStates.editing_own, F.data == "att:edit_save")
async def edit_own_save(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    session_id = data.get("session_id")
    items = data.get("items", {})
    original_state = data.get("original_state", {})
    class_id = data.get("class_id")
    school_id = data.get("school_id")
    class_name = data.get("class_name", "?")

    if not session_id or not items or class_id is None or school_id is None:
        await callback.answer("Сессия истекла, начните заново.", show_alert=True)
        await state.clear()
        return

    # Вычисляем diff: кто изменился относительно исходного состояния
    changes: list[tuple[str, bool]] = []
    for student_id, item in items.items():
        old_present = original_state.get(student_id)
        new_present = item["is_present"]
        if old_present is not None and old_present != new_present:
            changes.append((item["name"], new_present))

    # Сохраняем в БД
    updates: list[tuple[int, bool, str | None]] = []
    for student_id, item in items.items():
        if item["is_present"]:
            updates.append((student_id, True, None))
        else:
            # Сохраняем прежнюю причину, если была
            updates.append((student_id, False, item.get("reason")))

    update_session_records(session_id, updates)

    notify = getattr(callback.bot, "notify_web", None)
    if notify:
        await notify("summary_update")

    # Уведомляем классного руководителя, если есть изменения и это не он сам
    if changes:
        class_teacher = get_class_teacher_for_class(class_id, school_id)
        if class_teacher and class_teacher.telegram_id != callback.from_user.id:
            notify_lines = [f"📋 В вашем классе {class_name} внесены изменения:"]
            for name, is_present in changes:
                status = "присутствует" if is_present else "отсутствует"
                notify_lines.append(f"• {name} — {status}")
            # Если появились новые отсутствующие — просим отметить причины
            if any(not is_present for _, is_present in changes):
                notify_lines.append("\nОтметьте причины отсутствующим в разделе «Мой класс».")
            try:
                await callback.bot.send_message(
                    class_teacher.telegram_id,
                    "\n".join(notify_lines),
                )
            except Exception:
                pass

    await state.clear()
    await callback.answer("✅ Сохранено")

    # Перерисовываем карточку учителя
    card_data = get_today_session_card_data(callback.from_user.id)
    if card_data:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✏️ Исправить",
                callback_data=f"att:edit_own:{card_data['session_id']}",
            )],
            [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")],
        ])
        await callback.message.edit_text(card_data["text"], reply_markup=kb)
    else:
        await callback.message.edit_text("✅ Перекличка обновлена.", reply_markup=None)


@attendance_router.callback_query(AttendanceStates.editing_own, F.data == "att:edit_cancel")
async def edit_own_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Изменения отменены")

    card_data = get_today_session_card_data(callback.from_user.id)
    if card_data:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✏️ Исправить",
                callback_data=f"att:edit_own:{card_data['session_id']}",
            )],
            [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")],
        ])
        await callback.message.edit_text(card_data["text"], reply_markup=kb)
    else:
        await callback.message.edit_text("Карточка недоступна.", reply_markup=None)


async def _render_edit_own_keyboard(callback: CallbackQuery, state: FSMContext) -> None:
    """Рисует toggle-экран редактирования переклички учителя."""
    data = await state.get_data()
    items = data.get("items", {})
    class_name = data.get("class_name", "?")

    if not items:
        await callback.message.edit_text(
            "В классе нет учеников.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")],
            ]),
        )
        return

    kb_rows = []
    for student_id, item in items.items():
        icon = "✅" if item["is_present"] else "❌"
        kb_rows.append([InlineKeyboardButton(
            text=f"{icon} {item['name']}",
            callback_data=f"att:edit_toggle:{student_id}",
        )])

    kb_rows.append([
        InlineKeyboardButton(text="✅ Сохранить", callback_data="att:edit_save"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="att:edit_cancel"),
    ])

    text = (
        f"✏️ Редактирование переклички — класс {class_name}\n\n"
        f"✅ — присутствует, ❌ — отсутствует\n"
        f"Нажмите на ученика, чтобы изменить статус:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
    )