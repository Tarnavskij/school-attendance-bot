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
    get_class_session_today,
    try_acquire_editor_lock,
    check_edit_deadline,
    release_editor_lock,
)
from core.keyboards import BTN_START_ROLL, build_menu_keyboard
from core.roles import check_access, Role, is_admin
from core.school_context import get_school_id_for_admin
from helpers.session_card import get_today_session_card_data

attendance_router = Router()


class AttendanceStates(StatesGroup):
    choosing_class = State()
    choosing_mode = State()
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
            if card_data["can_edit"]:
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

    available = get_available_classes(date.today(), school_id=school_id, teacher_id=teacher.id)
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

def _build_mode_keyboard(class_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора режима переклички для нового класса."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="👥 Весь класс",
            callback_data=f"att:mode:full:{class_id}",
        )],
        [InlineKeyboardButton(
            text="👤 Только моя подгруппа",
            callback_data=f"att:mode:subgroup:{class_id}",
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="att:cancel_flow")],
    ])

@attendance_router.message(AttendanceStates.choosing_class)
async def text_during_class_choice(message: Message) -> None:
    await message.delete()


@attendance_router.message(AttendanceStates.choosing_mode)
async def text_during_mode_choice(message: Message) -> None:
    await message.delete()


@attendance_router.callback_query(AttendanceStates.choosing_class, F.data == "att:cancel_flow")
@attendance_router.callback_query(AttendanceStates.choosing_mode, F.data == "att:cancel_flow")
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

    # Проверяем: есть ли уже сессия по этому классу?
    existing = get_class_session_today(class_id, date.today(), school_id)

    if existing is None:
        # Нет сессии → показываем экран выбора режима
        await state.update_data(class_id=class_id, school_id=school_id)
        await state.set_state(AttendanceStates.choosing_mode)
        await callback.message.edit_text(
            "🏫 Выберите режим переклички:",
            reply_markup=_build_mode_keyboard(class_id),
        )
        await callback.answer()
        return

    # Сессия уже есть. Возможные статусы:
    # - active   → сюда не должны попасть (get_available_classes не показывает активные)
    # - partial  → B присоединяется, идём в toggle
    # - completed/auto_completed → тоже не показываются

    if existing["status"] != "partial":
        await callback.message.edit_text(
            "Этот класс уже недоступен для переклички.",
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=build_menu_keyboard(callback.from_user.id),
        )
        await state.clear()
        await callback.answer()
        return

    # Partial — присоединяемся как B
    # 1) Пытаемся взять lock
    lock_result = try_acquire_editor_lock(existing["id"], teacher.id)
    if lock_result in ("busy",):
        # Кто-то уже работает
        from repositories import get_editor_info
        editor = get_editor_info(existing["id"])
        editor_name = editor["name"] if editor else "другой учитель"
        await callback.answer(f"Учитель {editor_name} сейчас отмечает, попробуйте позже.", show_alert=True)
        await state.clear()
        return

    if lock_result == "closed":
        await callback.answer("Сессия не найдена.", show_alert=True)
        await state.clear()
        return

    # 2) Заполняем draft из существующих records
    students = get_students_by_class(class_id, school_id=school_id)
    records_map = {r["student_id"]: r for r in existing["records"]}

    draft_items: dict[int, dict] = {}
    original_state: dict[int, bool] = {}
    for s in students:
        rec = records_map.get(s.id)
        if rec:
            draft_items[s.id] = {
                "name": s.name,
                "is_present": rec["is_present"],
                "reason": rec["reason"],
                "marked_by": rec.get("marked_by_teacher_id"),
            }
            original_state[s.id] = rec["is_present"]
        else:
            # Ученик без записи — по умолчанию ✅
            draft_items[s.id] = {
                "name": s.name,
                "is_present": True,
                "reason": None,
                "marked_by": None,
            }
            original_state[s.id] = True

    await state.update_data(
        session_id=existing["id"],
        class_id=class_id,
        school_id=school_id,
        mode="partial_join",
        draft_items=draft_items,
        original_state=original_state,
        teacher_id=teacher.id,
    )

    # 3) Шапка: сколько уже отметил A
    existing_absent = sum(1 for r in existing["records"] if not r["is_present"])
    header = f"Учитель (уже отметил: {existing_absent} отсутствующих).\n" \
             f"✅ — присутствует   ❌ — отсутствует\n\nНажмите на ученика, чтобы изменить статус:"

    kb = _render_draft_keyboard(draft_items, existing["id"], editor_teacher_id=teacher.id)

    await callback.message.edit_text(header, reply_markup=kb)
    await state.set_state(AttendanceStates.marking)
    await callback.answer()

@attendance_router.callback_query(AttendanceStates.choosing_mode, F.data.startswith("att:mode:"))
async def mode_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Обрабатывает выбор режима переклички:
      att:mode:full:<class_id>      → «Весь класс»
      att:mode:subgroup:<class_id>  → «Только моя подгруппа»
    """
    parts = callback.data.split(":")
    # parts = ["att", "mode", "full"|"subgroup", "<class_id>"]
    mode_type = parts[2]
    class_id = int(parts[3])

    teacher = get_teacher_by_telegram_id(callback.from_user.id)
    if not teacher:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return

    data = await state.get_data()
    school_id = data.get("school_id")
    if school_id is None:
        # fallback для админа
        if is_admin(callback.from_user.id):
            school_id = get_school_id_for_admin(callback.from_user.id)
        else:
            school_id = teacher.school_id

    # Создаём сессию (active)
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

    # Захватываем lock (защита от гонок; при active и так никто не увидит,
    # но для единообразия)
    try_acquire_editor_lock(session.id, teacher.id)

    mode = "new_all" if mode_type == "full" else "new_partial"

    # Загружаем свежесозданные записи (add_records создал их как present=True)
    students = get_students_by_class(class_id, school_id=school_id)
    records = get_session_records(session.id)
    records_map = {r.student_id: r for r in records}

    draft_items: dict[int, dict] = {}
    original_state: dict[int, bool] = {}
    for s in students:
        rec = records_map.get(s.id)
        if rec:
            draft_items[s.id] = {
                "name": s.name,
                "is_present": rec.is_present,
                "reason": rec.reason,
                "marked_by": getattr(rec, "marked_by_teacher_id", None),
            }
            original_state[s.id] = rec.is_present
        else:
            draft_items[s.id] = {
                "name": s.name,
                "is_present": True,
                "reason": None,
                "marked_by": None,
            }
            original_state[s.id] = True

    await state.update_data(
        session_id=session.id,
        class_id=class_id,
        school_id=school_id,
        mode=mode,
        draft_items=draft_items,
        original_state=original_state,
    )

    kb = _render_draft_keyboard(draft_items, session.id, editor_teacher_id=teacher.id)

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

    # Проверка deadline
    ok, reason = check_edit_deadline(session_id)
    if not ok:
        await callback.answer(
            "Время редактирования истекло. Изменения не сохранены.",
            show_alert=True,
        )
        await state.clear()
        return

    # Проверка lock: только текущий editor может менять draft
    # (полагаемся на то, что мы вошли в toggle и держали lock с момента входа)
    draft_items = data.get("draft_items", {})
    if student_id not in draft_items:
        await callback.answer("Ученик не найден.", show_alert=True)
        return

    item = draft_items[student_id]

    # Заглушка: чужой ❌ (marked_by != наш teacher_id)
    teacher = get_teacher_by_telegram_id(callback.from_user.id)
    if teacher and not item["is_present"] and item["marked_by"] not in (None, teacher.id):
        await callback.answer("Отмечено другим учителем", show_alert=False)
        return

    # Меняем is_present в draft
    item["is_present"] = not item["is_present"]
    # Если стали present — owner сбрасывается (мы "передумали")
    if item["is_present"]:
        item["marked_by"] = None
    # Если стали absent — пока owner не ставим, это произойдёт при submit

    await state.update_data(draft_items=draft_items)

    editor_teacher_id = teacher.id if teacher else None
    kb = _render_draft_keyboard(draft_items, session_id, editor_teacher_id=editor_teacher_id)
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

    mode = data.get("mode", "new_all")

    teacher = get_teacher_by_telegram_id(callback.from_user.id)

    if mode in ("new_all", "new_partial"):
        # Учитель отменил свою новую сессию — удаляем полностью
        if teacher:
            release_editor_lock(session_id, teacher.id)
        delete_session(session_id)
        await callback.message.edit_text("Перекличка отменена.")

    elif mode == "partial_join":
        # B отменил участие — сессия остаётся partial, изменения B не сохраняются
        if teacher:
            release_editor_lock(session_id, teacher.id)
        await callback.message.edit_text("Отмена. Изменения не сохранены.")

    else:
        # Не должны сюда попасть, но на всякий случай
        if teacher:
            release_editor_lock(session_id, teacher.id)
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

    data = await state.get_data()
    expected_session_id = data.get("session_id")
    if expected_session_id is None or session_id != expected_session_id:
        await callback.answer("Сессия недействительна.", show_alert=True)
        return

    draft_items = data.get("draft_items", {})
    original_state = data.get("original_state", {})
    mode = data.get("mode", "new_all")

    if not draft_items:
        await callback.answer("Нет данных для отправки.", show_alert=True)
        return

    teacher = get_teacher_by_telegram_id(callback.from_user.id)
    if not teacher:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        await state.clear()
        return

    # Собираем all_records и changed_student_ids
    all_records: list[tuple[int, bool, str | None]] = []
    changed_student_ids: list[int] = []
    for sid, item in draft_items.items():
        is_present = item["is_present"]
        reason = item.get("reason")
        if is_present:
            all_records.append((sid, True, None))
        else:
            all_records.append((sid, False, reason))

        # Изменился ли этот ученик относительно входа?
        old = original_state.get(sid)
        if old is not None and old != is_present:
            changed_student_ids.append(sid)

    # Отправляем через сервис
    ok, reason = await AttendanceService.submit_session(
        bot=callback.bot,
        session_id=session_id,
        teacher_id=teacher.id,
        all_records=all_records,
        changed_student_ids=changed_student_ids,
        mode=mode,
    )

    if not ok:
        # Обработка ошибок
        error_msgs = {
            "session_not_found": "Сессия не найдена.",
            "lock_busy": "Сессия занята другим учителем.",
            "deadline_expired": "Время редактирования истекло. Изменения не сохранены.",
            "session_closed": "Сессия уже закрыта.",
        }
        msg = error_msgs.get(reason, "Не удалось сохранить изменения.")
        await callback.answer(msg, show_alert=True)
        await state.clear()
        # Возврат в меню
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=build_menu_keyboard(callback.from_user.id),
        )
        return

    # Успех. Очищаем FSM
    await state.clear()

    # Определяем, какая карточка показывается
    card_data = get_today_session_card_data(callback.from_user.id)

    if mode == "new_partial":
        # Первый участник подгруппы — сессия partial. Показываем карточку «частично».
        if card_data:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✏️ Исправить",
                    callback_data=f"att:edit_own:{card_data['session_id']}",
                )],
                [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")],
            ]) if card_data["can_edit"] else None

            await callback.message.edit_text(card_data["text"], reply_markup=kb)
        else:
            await callback.message.edit_text("✅ Ваша часть сохранена.")
        await callback.answer("Отправлено! Ожидаем второго учителя.")
        return

    # mode == "new_all" или "partial_join" — completed
    # Показываем карточку с результатом
    if card_data:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✏️ Исправить",
                callback_data=f"att:edit_own:{card_data['session_id']}",
            )],
            [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")],
        ]) if card_data["can_edit"] else None

        await callback.message.edit_text(card_data["text"], reply_markup=kb)
    else:
        await callback.message.edit_text("✅ Перекличка завершена.")

    await callback.answer("Готово!")


def _build_marking_keyboard(
    students,
    session_id: int,
    records,
    editor_teacher_id: int | None = None,
) -> InlineKeyboardMarkup:
    """
    Клавиатура toggle-экрана.

    students — список StudentDTO
    records  — список словарей с ключами student_id, is_present, reason,
               marked_by_teacher_id (из get_class_session_today)
               ИЛИ список RecordDTO — для обратной совместимости
               обрабатываем оба варианта через .get() / getattr
    editor_teacher_id — если задан и в partial-режиме, чужие ❌ блокируются
    """
    # Нормализуем records в словарь {student_id: {is_present, marked_by}}
    rec_map: dict[int, dict] = {}
    for r in records:
        if isinstance(r, dict):
            rec_map[r["student_id"]] = {
                "is_present": r["is_present"],
                "marked_by": r.get("marked_by_teacher_id"),
            }
        else:
            # RecordDTO
            rec_map[r.student_id] = {
                "is_present": r.is_present,
                "marked_by": getattr(r, "marked_by_teacher_id", None),
            }

    buttons = []
    for s in students:
        rec = rec_map.get(s.id)
        if rec is None:
            # Ученик без записи — по умолчанию ✅
            text = f"✅ {s.name}"
            cb = f"att:toggle:{session_id}:{s.id}"
        else:
            is_present = rec["is_present"]
            marked_by = rec["marked_by"]

            # Заглушка: чужой ❌ в partial-режиме
            locked = (
                editor_teacher_id is not None
                and not is_present
                and marked_by is not None
                and marked_by != editor_teacher_id
            )

            icon = "✅" if is_present else "❌"
            if locked:
                text = f"{icon} {s.name} (🔒)"
                cb = f"att:locked:{session_id}:{s.id}"
            else:
                text = f"{icon} {s.name}"
                cb = f"att:toggle:{session_id}:{s.id}"

        buttons.append([InlineKeyboardButton(text=text, callback_data=cb)])

    buttons.append([
        InlineKeyboardButton(text="✅ Отправить", callback_data=f"att:submit:{session_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"att:cancel:{session_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Обработчик заглушки: просто сообщаем, что отмечено другим
@attendance_router.callback_query(F.data.startswith("att:locked:"))
async def locked_student(callback: CallbackQuery) -> None:
    await callback.answer("Отмечено другим учителем", show_alert=False)


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

    session = get_teacher_session_today(teacher.id, date.today(), school_id=teacher.school_id)
    if not session or session.id != session_id:
        await callback.answer("Сессия не найдена.", show_alert=True)
        return

    # Разрешаем completed и partial (если учитель — участник partial)
    if session.status == "auto_completed":
        await callback.answer("Перекличка закрыта автоматически, редактирование недоступно.", show_alert=True)
        return

    if session.status == "partial":
        if not session.participant_ids or teacher.id not in session.participant_ids:
            await callback.answer("Вы не участвовали в этой перекличке.", show_alert=True)
            return

    # Проверка deadline (finalize_at)
    ok, reason = check_edit_deadline(session_id)
    if not ok:
        msg = "Время редактирования истекло." if reason == "deadline_expired" else "Сессия недоступна."
        await callback.answer(msg, show_alert=True)
        return

    # Пытаемся взять lock
    lock_result = try_acquire_editor_lock(session_id, teacher.id)
    if lock_result == "busy":
        from repositories import get_editor_info
        editor = get_editor_info(session_id)
        editor_name = editor["name"] if editor else "другой учитель"
        await callback.answer(f"Учитель {editor_name} сейчас отмечает, попробуйте позже.", show_alert=True)
        return
    if lock_result == "closed":
        await callback.answer("Сессия не найдена.", show_alert=True)
        return

    # Заполняем items из records
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
                "marked_by": getattr(rec, "marked_by_teacher_id", None),
            }
        else:
            items[s.id] = {
                "name": s.name,
                "is_present": True,
                "reason": None,
                "marked_by": None,
            }

    original_state = {sid: it["is_present"] for sid, it in items.items()}

    await state.update_data(
        session_id=session_id,
        class_id=session.class_id,
        school_id=teacher.school_id,
        class_name=session.class_name,
        items=items,
        original_state=original_state,
        editor_teacher_id=teacher.id,
        session_status=session.status,
    )
    await state.set_state(AttendanceStates.editing_own)

    await _render_edit_own_keyboard(callback, state)
    await callback.answer()


@attendance_router.callback_query(AttendanceStates.editing_own, F.data.startswith("att:edit_toggle:"))
async def edit_own_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    student_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    items = data.get("items", {})
    session_id = data.get("session_id")
    session_status = data.get("session_status", "completed")
    editor_teacher_id = data.get("editor_teacher_id")

    if student_id not in items:
        await callback.answer("Ученик не найден.", show_alert=True)
        return

    # Проверка deadline
    if session_id:
        ok, _ = check_edit_deadline(session_id)
        if not ok:
            await callback.answer("Время редактирования истекло.", show_alert=True)
            await state.clear()
            return

    # Проверка lock: мы всё ещё редактор?
    if session_id:
        from repositories import get_editor_info
        editor = get_editor_info(session_id)
        if editor is not None and editor["teacher_id"] != editor_teacher_id:
            await callback.answer(
                f"Сессию редактирует {editor['name']}, попробуйте позже.",
                show_alert=True,
            )
            await state.clear()
            return

    item = items[student_id]

    # Заглушка: partial + чужой ❌
    if (
        session_status == "partial"
        and not item["is_present"]
        and item.get("marked_by") not in (None, editor_teacher_id)
    ):
        await callback.answer("Отмечено другим учителем", show_alert=False)
        return

    # Меняем is_present
    item["is_present"] = not item["is_present"]
    if item["is_present"]:
        item["marked_by"] = None

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
    editor_teacher_id = data.get("editor_teacher_id")

    if not session_id or not items or class_id is None or school_id is None:
        await callback.answer("Сессия истекла, начните заново.", show_alert=True)
        await state.clear()
        return

    teacher = get_teacher_by_telegram_id(callback.from_user.id)
    if not teacher:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        await state.clear()
        return

    # Собираем all_records и changed_student_ids
    all_records: list[tuple[int, bool, str | None]] = []
    changed_student_ids: list[int] = []
    changes: list[tuple[str, bool]] = []
    for student_id, item in items.items():
        is_present = item["is_present"]
        reason = item.get("reason")
        if is_present:
            all_records.append((student_id, True, None))
        else:
            all_records.append((student_id, False, reason))

        old_present = original_state.get(student_id)
        if old_present is not None and old_present != is_present:
            changed_student_ids.append(student_id)
            changes.append((item["name"], is_present))

    # Сохраняем через service
    ok, reason = await AttendanceService.submit_session(
        bot=callback.bot,
        session_id=session_id,
        teacher_id=teacher.id,
        all_records=all_records,
        changed_student_ids=changed_student_ids,
        mode="edit",
    )

    if not ok:
        error_msgs = {
            "session_not_found": "Сессия не найдена.",
            "lock_busy": "Сессия занята другим учителем.",
            "deadline_expired": "Время редактирования истекло.",
            "session_closed": "Сессия уже закрыта.",
        }
        msg = error_msgs.get(reason, "Не удалось сохранить изменения.")
        await callback.answer(msg, show_alert=True)
        await state.clear()
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=build_menu_keyboard(callback.from_user.id),
        )
        return

    # Уведомление class_teacher об изменениях (не о завершении — оно уже было)
    if changes:
        class_teacher = get_class_teacher_for_class(class_id, school_id)
        if class_teacher and class_teacher.telegram_id != callback.from_user.id:
            notify_lines = [f"📋 В вашем классе {class_name} внесены изменения:"]
            for name, is_present in changes:
                status = "присутствует" if is_present else "отсутствует"
                notify_lines.append(f"• {name} — {status}")
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
        kb = None
        if card_data["can_edit"]:
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
    data = await state.get_data()
    session_id = data.get("session_id")
    editor_teacher_id = data.get("editor_teacher_id")

    # Снимаем lock, если он наш
    if session_id and editor_teacher_id:
        teacher = get_teacher_by_telegram_id(callback.from_user.id)
        if teacher:
            release_editor_lock(session_id, teacher.id)

    await state.clear()
    await callback.answer("Изменения отменены")

    card_data = get_today_session_card_data(callback.from_user.id)
    if card_data:
        kb = None
        if card_data["can_edit"]:
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
    editor_teacher_id = data.get("editor_teacher_id")
    session_status = data.get("session_status", "completed")

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
        is_present = item["is_present"]
        marked_by = item.get("marked_by")

        # Заглушка: partial-режим + чужой ❌
        locked = (
            session_status == "partial"
            and not is_present
            and marked_by is not None
            and marked_by != editor_teacher_id
        )

        icon = "✅" if is_present else "❌"
        if locked:
            text = f"{icon} {item['name']} (🔒)"
            cb = f"att:locked:{data.get('session_id', 0)}:{student_id}"
        else:
            text = f"{icon} {item['name']}"
            cb = f"att:edit_toggle:{student_id}"

        kb_rows.append([InlineKeyboardButton(text=text, callback_data=cb)])

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

def _render_draft_keyboard(
    draft_items: dict,
    session_id: int,
    editor_teacher_id: int | None,
) -> InlineKeyboardMarkup:
    """
    Клавиатура toggle-экрана из draft_items (данные в FSM).

    draft_items: {student_id: {"name": str, "is_present": bool,
                              "reason": str | None, "marked_by": int | None}}
    """
    buttons = []
    for sid, item in draft_items.items():
        is_present = item["is_present"]
        marked_by = item["marked_by"]

        # Заглушка: чужой ❌ в partial-режиме
        locked = (
            editor_teacher_id is not None
            and not is_present
            and marked_by is not None
            and marked_by != editor_teacher_id
        )

        icon = "✅" if is_present else "❌"
        if locked:
            text = f"{icon} {item['name']} (🔒)"
            cb = f"att:locked:{session_id}:{sid}"
        else:
            text = f"{icon} {item['name']}"
            cb = f"att:toggle:{session_id}:{sid}"

        buttons.append([InlineKeyboardButton(text=text, callback_data=cb)])

    buttons.append([
        InlineKeyboardButton(text="✅ Отправить", callback_data=f"att:submit:{session_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"att:cancel:{session_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)