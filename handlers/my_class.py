# handlers/my_class.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from datetime import date

from repositories import (
    get_teacher_by_telegram_id,
    get_all_classes,
    get_students_by_class,
    get_absent_students_today,
    set_absence_reason,
    get_default_school_id,
    get_class_session_today,
    update_session_records,
    try_acquire_editor_lock,
    get_editor_info,
    release_editor_lock,
)
from core.keyboards import BTN_MY_CLASS, build_menu_keyboard, back_to_menu_btn
from core.roles import check_access, is_admin, Role
from core.constants import ABSENCE_REASONS
from core.school_context import get_school_id_for_admin
from services import AttendanceService

my_class_router = Router()


class MyClassStates(StatesGroup):
    editing = State()


@my_class_router.message(F.text == BTN_MY_CLASS)
async def my_class_handler(message: Message) -> None:
    user_id = message.from_user.id
    if not check_access(user_id, [Role.CLASS_TEACHER]):
        await message.answer("У вас нет закреплённого класса.")
        return

    if is_admin(user_id):
        school_id = get_school_id_for_admin(user_id)
        classes = get_all_classes(school_id)
        if not classes:
            await message.answer("Нет доступных классов.")
            return
        kb = _build_class_grid_keyboard(classes, callback_prefix="mc:view")
        await message.answer("Выберите класс для просмотра:", reply_markup=kb)
        return

    teacher = get_teacher_by_telegram_id(user_id)
    if not teacher or not teacher.class_id:
        await message.answer("У вас не указан класс. Обратитесь к администратору.")
        return

    await _show_absent_list(message, teacher.class_id, teacher.school_id, edit=False)


@my_class_router.callback_query(F.data.startswith("mc:view:"))
async def view_class(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    if not check_access(user_id, [Role.CLASS_TEACHER]):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    class_id = int(callback.data.split(":")[-1])
    school_id = _get_school_id(user_id)
    await _show_absent_list(callback.message, class_id, school_id, edit=True)
    await callback.answer()

@my_class_router.callback_query(F.data.startswith("mc:refresh:"))
async def refresh_class(callback: CallbackQuery) -> None:
    """Перерисовывает экран класса (для кнопки «Обновить» на partial-экране)."""
    user_id = callback.from_user.id
    if not check_access(user_id, [Role.CLASS_TEACHER]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    class_id = int(callback.data.split(":")[-1])
    school_id = _get_school_id(user_id)

    await _show_absent_list(callback.message, class_id, school_id, edit=True)
    await callback.answer("Обновлено")

@my_class_router.callback_query(F.data.startswith("mc:reason_menu:"))
async def show_reason_menu(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    if not check_access(user_id, [Role.CLASS_TEACHER]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    _, _, student_id_str, class_id_str = callback.data.split(":")
    student_id = int(student_id_str)
    class_id = int(class_id_str)

    if not is_admin(user_id):
        teacher = get_teacher_by_telegram_id(user_id)
        if not teacher or teacher.class_id != class_id:
            await callback.answer("Это не ваш класс.", show_alert=True)
            return

    school_id = _get_school_id(user_id)

    absent = get_absent_students_today(class_id, date.today(), school_id=school_id)
    student_info = absent.get(student_id)
    student_name = student_info["name"] if student_info else f"ID {student_id}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        *[
            [InlineKeyboardButton(text=r, callback_data=f"mc:reason:{student_id}:{class_id}:{i}")]
            for i, r in enumerate(ABSENCE_REASONS)
        ],
        [InlineKeyboardButton(text="↩️ Назад", callback_data=f"mc:view:{class_id}")],
    ])
    await callback.message.edit_text(
        f"Выберите причину отсутствия для {student_name}:",
        reply_markup=kb,
    )
    await callback.answer()


@my_class_router.callback_query(F.data.startswith("mc:reason:"))
async def apply_reason(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    if not check_access(user_id, [Role.CLASS_TEACHER]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = callback.data.split(":")
    student_id = int(parts[2])
    class_id = int(parts[3])
    reason_idx = int(parts[4])

    if reason_idx < 0 or reason_idx >= len(ABSENCE_REASONS):
        await callback.answer("Недопустимая причина.", show_alert=True)
        return
    reason = ABSENCE_REASONS[reason_idx]
    school_id = _get_school_id(user_id)

    if not is_admin(user_id):
        teacher = get_teacher_by_telegram_id(user_id)
        if not teacher or teacher.class_id != class_id:
            await callback.answer("Это не ваш класс.", show_alert=True)
            return

    set_absence_reason(student_id, class_id, date.today(), reason, school_id=school_id)
    await callback.answer("Причина сохранена.")
    await _show_absent_list(callback.message, class_id, school_id, edit=True)


def _get_school_id(user_id: int) -> int:
    """Возвращает school_id: для админа глобальный, для учителя из профиля."""
    if is_admin(user_id):
        return get_school_id_for_admin(user_id)
    teacher = get_teacher_by_telegram_id(user_id)
    return teacher.school_id if teacher else get_default_school_id()  # <-- заменили DEFAULT_SCHOOL_ID


def _build_class_grid_keyboard(classes, callback_prefix: str) -> InlineKeyboardMarkup:
    groups: dict[int, list] = {}
    for c in classes:
        grade = c.grade or 0
        groups.setdefault(grade, []).append(c)
    rows = []
    for grade in sorted(groups.keys()):
        buttons = [InlineKeyboardButton(text=c.name, callback_data=f"{callback_prefix}:{c.id}") for c in groups[grade]]
        rows.append(buttons)
    rows.append([back_to_menu_btn()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_absent_list(message: Message, class_id: int, school_id: int, edit: bool = False) -> None:
    today = date.today()
    session = get_class_session_today(class_id, today, school_id)
    absent = get_absent_students_today(class_id, today, school_id=school_id)

    classes = get_all_classes(school_id)
    class_obj = next((c for c in classes if c.id == class_id), None)
    class_name = class_obj.name if class_obj else "?"

    # Случай 1: перекличка сегодня не проводилась
    if session is None:
        text = f"📋 В классе {class_name} сегодня перекличка не проводилась."
        kb = InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]])
        await _send_or_edit(message, text, kb, edit)
        return

    # Случай 2: перекличка ещё идёт
    if session["status"] == "active":
        text = f"⏳ В классе {class_name} перекличка ещё идёт. Дождитесь завершения."
        kb = InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]])
        await _send_or_edit(message, text, kb, edit)
        return

    # Случай 2.5: partial — отмечена часть класса
    if session["status"] == "partial":
        # Проверяем: не является ли class_teacher сам участником
        teacher = get_teacher_by_telegram_id(message.from_user.id) if hasattr(message, "from_user") else None
        # Для callback это message.from_user
        # Для message (не callback) — message.from_user тоже есть

        user_id = None
        if hasattr(message, "from_user") and message.from_user:
            user_id = message.from_user.id
        current_teacher = get_teacher_by_telegram_id(user_id) if user_id else None

        is_participant = (
            current_teacher is not None
            and session["participant_ids"]
            and current_teacher.id in session["participant_ids"]
        )

        # Считаем количество отсутствующих
        absent_count = sum(1 for r in session["records"] if not r["is_present"])

        # Имя первого участника
        participant_name = (
            session["participant_names"][0]
            if session["participant_names"]
            else "учитель"
        )

        lines = [
            f"📋 В классе {class_name} отмечена часть класса.",
            f"Отметил: {participant_name}.",
            f"Отсутствуют: {absent_count}.",
        ]
        text = "\n".join(lines)

        if is_participant:
            # Class_teacher сам участник — работает как обычный редактор
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✏️ Исправить",
                    callback_data=f"mc:edit:{class_id}",
                )],
                [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"mc:refresh:{class_id}")],
                [back_to_menu_btn()],
            ])
        else:
            # Class_teacher — не участник, работает как B
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✏️ Дополнить",
                    callback_data=f"mc:edit:{class_id}",
                )],
                [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"mc:refresh:{class_id}")],
                [back_to_menu_btn()],
            ])

        await _send_or_edit(message, text, kb, edit)
        return

    # Случай 3: перекличка закрыта автоматически (в 20:00) — только просмотр
    if session["status"] == "auto_completed":
        lines = [f"🔒 Перекличка в классе {class_name} закрыта автоматически."]
        if absent:
            lines.append(f"Отсутствуют ({len(absent)}):")
            for info in absent.values():
                reason = info["reason"] or "причина не указана"
                lines.append(f"• {info['name']} — {reason}")
        else:
            lines.append("✅ Все присутствовали.")
        text = "\n".join(lines)
        kb = InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]])
        await _send_or_edit(message, text, kb, edit)
        return

    # Случай 4: перекличка завершена (status == "completed") — можно редактировать
    edit_btn = InlineKeyboardButton(
        text="✏️ Редактировать",
        callback_data=f"mc:edit:{class_id}",
    )

    if not absent:
        text = f"✅ В классе {class_name} все присутствовали."
        kb = InlineKeyboardMarkup(inline_keyboard=[[edit_btn, back_to_menu_btn()]])
    else:
        rows = []
        for student_id, info in absent.items():
            label = info["name"]
            if info["reason"]:
                label += f" ({info['reason']})"
            rows.append([InlineKeyboardButton(
                text=label,
                callback_data=f"mc:reason_menu:{student_id}:{class_id}",
            )])
        rows.append([edit_btn, back_to_menu_btn()])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        text = f"📋 Отсутствующие в классе {class_name} (нажмите для указания причины):"

    await _send_or_edit(message, text, kb, edit)


async def _send_or_edit(message: Message, text: str, kb: InlineKeyboardMarkup, edit: bool) -> None:
    """Отправляет новое сообщение или редактирует текущее — убирает 4 копипаста."""
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)

# ── Редактор переклички (для классного руководителя и админа) ──────────────

@my_class_router.callback_query(F.data.startswith("mc:edit:"))
async def mc_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    if not check_access(user_id, [Role.CLASS_TEACHER]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    class_id = int(callback.data.split(":")[-1])
    school_id = _get_school_id(user_id)

    teacher = get_teacher_by_telegram_id(user_id)
    if not teacher:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return

    if not is_admin(user_id):
        if teacher.class_id != class_id:
            await callback.answer("Это не ваш класс.", show_alert=True)
            return

    session = get_class_session_today(class_id, date.today(), school_id)
    if not session:
        await callback.answer("Перекличка не проводилась.", show_alert=True)
        return

    # Разрешаем partial и completed. auto_completed — нет.
    if session["status"] not in ("partial", "completed"):
        await callback.answer("Перекличка недоступна для редактирования.", show_alert=True)
        return

    # Пытаемся взять lock
    lock_result = try_acquire_editor_lock(session["id"], teacher.id)
    if lock_result == "busy":
        editor = get_editor_info(session["id"])
        editor_name = editor["name"] if editor else "другой учитель"
        await callback.answer(
            f"Сессию редактирует {editor_name}, попробуйте позже.",
            show_alert=True,
        )
        return
    if lock_result == "closed":
        await callback.answer("Сессия не найдена.", show_alert=True)
        return

    # Определяем, редактирует ли class_teacher свою часть (partial + participant)
    is_participant = (
        session["status"] == "partial"
        and session["participant_ids"]
        and teacher.id in session["participant_ids"]
    )

    students = get_students_by_class(class_id, school_id)
    records_map = {r["student_id"]: r for r in session["records"]}

    items: dict[int, dict] = {}
    for s in students:
        rec = records_map.get(s.id)
        if rec:
            items[s.id] = {
                "name": s.name,
                "is_present": rec["is_present"],
                "reason": rec["reason"],
                "marked_by": rec.get("marked_by_teacher_id"),
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
        session_id=session["id"],
        class_id=class_id,
        school_id=school_id,
        class_name=session["class_name"],
        items=items,
        original_state=original_state,
        editor_teacher_id=teacher.id,
        session_status=session["status"],
        is_participant=is_participant,
    )
    await state.set_state(MyClassStates.editing)

    await _render_edit_keyboard(callback, state)
    await callback.answer()


@my_class_router.callback_query(MyClassStates.editing, F.data.startswith("mc:toggle:"))
async def mc_toggle_student(callback: CallbackQuery, state: FSMContext) -> None:
    student_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    items = data.get("items", {})
    session_id = data.get("session_id")
    session_status = data.get("session_status", "completed")
    editor_teacher_id = data.get("editor_teacher_id")

    if student_id not in items:
        await callback.answer("Ученик не найден.", show_alert=True)
        return

    # Проверка lock: мы всё ещё редактор?
    if session_id:
        editor = get_editor_info(session_id)
        if editor is not None and editor["teacher_id"] != editor_teacher_id:
            await callback.answer(
                f"Сессию редактирует {editor['name']}, попробуйте позже.",
                show_alert=True,
            )
            await state.clear()
            return

    item = items[student_id]

    # Заглушка для partial
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
    await _render_edit_keyboard(callback, state)
    await callback.answer()


@my_class_router.callback_query(MyClassStates.editing, F.data == "mc:save")
async def mc_save(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    session_id = data.get("session_id")
    items = data.get("items", {})
    class_id = data.get("class_id")
    school_id = data.get("school_id")
    original_state = data.get("original_state", {})
    session_status = data.get("session_status", "completed")
    is_participant = data.get("is_participant", False)
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

    # Определяем mode
    # - partial + не participant → class_teacher работает как B → partial_join
    # - partial + participant    → правит свою часть → edit
    # - completed                → полное редактирование → edit
    if session_status == "partial" and not is_participant:
        mode = "partial_join"
    else:
        mode = "edit"

    ok, reason = await AttendanceService.submit_session(
        bot=callback.bot,
        session_id=session_id,
        teacher_id=teacher.id,
        all_records=all_records,
        changed_student_ids=changed_student_ids,
        mode=mode,
        skip_deadline=True,  # class_teacher не ограничен 45 минутами
    )

    if not ok:
        error_msgs = {
            "session_not_found": "Сессия не найдена.",
            "lock_busy": "Сессия занята другим учителем.",
            "session_closed": "Сессия уже закрыта.",
        }
        msg = error_msgs.get(reason, "Не удалось сохранить.")
        await callback.answer(msg, show_alert=True)
        await state.clear()
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=build_menu_keyboard(callback.from_user.id),
        )
        return

    await state.clear()
    await callback.answer("✅ Сохранено")

    # Перерисовываем экран «Мой класс»
    await _show_absent_list(callback.message, class_id, school_id, edit=True)


@my_class_router.callback_query(MyClassStates.editing, F.data == "mc:cancel_edit")
async def mc_cancel_edit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    session_id = data.get("session_id")
    class_id = data.get("class_id")
    school_id = data.get("school_id")
    editor_teacher_id = data.get("editor_teacher_id")

    # Снимаем lock, если он наш
    if session_id and editor_teacher_id:
        teacher = get_teacher_by_telegram_id(callback.from_user.id)
        if teacher:
            release_editor_lock(session_id, teacher.id)

    await state.clear()
    await callback.answer("Отменено")

    if class_id is not None and school_id is not None:
        await _show_absent_list(callback.message, class_id, school_id, edit=True)
    else:
        await callback.message.edit_text("Редактирование отменено.", reply_markup=None)


async def _render_edit_keyboard(callback: CallbackQuery, state: FSMContext) -> None:
    """Рисует экран редактирования переклички (toggle-список учеников)."""
    data = await state.get_data()
    items = data.get("items", {})
    class_name = data.get("class_name", "?")
    session_id = data.get("session_id", 0)
    session_status = data.get("session_status", "completed")
    editor_teacher_id = data.get("editor_teacher_id")

    if not items:
        await callback.message.edit_text(
            "В классе нет учеников.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]]),
        )
        return

    kb_rows = []
    for student_id, item in items.items():
        is_present = item["is_present"]
        marked_by = item.get("marked_by")

        # Заглушка: partial + чужой ❌
        locked = (
            session_status == "partial"
            and not is_present
            and marked_by is not None
            and marked_by != editor_teacher_id
        )

        icon = "✅" if is_present else "❌"
        if locked:
            text = f"{icon} {item['name']} (🔒)"
            cb = f"att:locked:{session_id}:{student_id}"
        else:
            text = f"{icon} {item['name']}"
            cb = f"mc:toggle:{student_id}"

        kb_rows.append([InlineKeyboardButton(text=text, callback_data=cb)])

    kb_rows.append([
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="mc:save"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="mc:cancel_edit"),
    ])

    if session_status == "partial":
        header = f"✏️ Дополнение переклички — класс {class_name} (частично)\n\n"
    else:
        header = f"✏️ Редактирование переклички — класс {class_name}\n\n"

    text = (
        header
        + "✅ — присутствует, ❌ — отсутствует\n"
        + "Нажмите на ученика, чтобы изменить статус:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
    )