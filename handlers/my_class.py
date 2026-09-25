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
)
from core.keyboards import BTN_MY_CLASS, build_menu_keyboard, back_to_menu_btn
from core.roles import check_access, is_admin, Role
from core.constants import ABSENCE_REASONS
from core.school_context import get_school_id_for_admin

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

    if not is_admin(user_id):
        teacher = get_teacher_by_telegram_id(user_id)
        if not teacher or teacher.class_id != class_id:
            await callback.answer("Это не ваш класс.", show_alert=True)
            return

    session = get_class_session_today(class_id, date.today(), school_id)
    if not session:
        await callback.answer("Перекличка не проводилась.", show_alert=True)
        return
    if session["status"] != "completed":
        await callback.answer("Перекличка недоступна для редактирования.", show_alert=True)
        return

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
            }
        else:
            # Ученик добавлен после переклички — по умолчанию присутствует
            items[s.id] = {"name": s.name, "is_present": True, "reason": None}

    await state.update_data(
        session_id=session["id"],
        class_id=class_id,
        school_id=school_id,
        class_name=session["class_name"],
        items=items,
    )
    await state.set_state(MyClassStates.editing)

    await _render_edit_keyboard(callback, state)
    await callback.answer()


@my_class_router.callback_query(MyClassStates.editing, F.data.startswith("mc:toggle:"))
async def mc_toggle_student(callback: CallbackQuery, state: FSMContext) -> None:
    student_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    items = data.get("items", {})
    if student_id in items:
        items[student_id]["is_present"] = not items[student_id]["is_present"]
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

    if not session_id or not items or class_id is None or school_id is None:
        await callback.answer("Сессия истекла, начните заново.", show_alert=True)
        await state.clear()
        return

    updates: list[tuple[int, bool, str | None]] = []
    for student_id, item in items.items():
        if item["is_present"]:
            updates.append((student_id, True, None))
        else:
            # Сохраняем прежнюю причину (если была)
            updates.append((student_id, False, item.get("reason")))

    update_session_records(session_id, updates)

    notify = getattr(callback.bot, "notify_web", None)
    if notify:
        await notify("summary_update")

    await state.clear()
    await callback.answer("✅ Сохранено")
    await _show_absent_list(callback.message, class_id, school_id, edit=True)


@my_class_router.callback_query(MyClassStates.editing, F.data == "mc:cancel_edit")
async def mc_cancel_edit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    class_id = data.get("class_id")
    school_id = data.get("school_id")
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

    if not items:
        await callback.message.edit_text(
            "В классе нет учеников.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]]),
        )
        return

    kb_rows = []
    for student_id, item in items.items():
        icon = "✅" if item["is_present"] else "❌"
        kb_rows.append([InlineKeyboardButton(
            text=f"{icon} {item['name']}",
            callback_data=f"mc:toggle:{student_id}",
        )])

    kb_rows.append([
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="mc:save"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="mc:cancel_edit"),
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