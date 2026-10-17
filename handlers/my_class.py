# handlers/my_class.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from datetime import date
from helpers.ui import reset_screen, set_screen

from repositories import (
    get_teacher_by_telegram_id,
    get_all_classes,
    get_students_by_class,
    get_absent_students_today,
    set_absence_reason,
    get_default_school_id,
    get_class_session_today,
    update_session_records,
    get_class_analytics,
    get_class_quarters_with_data,
)
from core.keyboards import (
    BTN_MY_CLASS, BTN_ANALYTICS, build_menu_keyboard, back_to_menu_btn,
)
from core.roles import check_access, is_admin, Role
from core.constants import ABSENCE_REASONS
from core.school_context import get_school_id_for_admin

my_class_router = Router()


class MyClassStates(StatesGroup):
    editing = State()


@my_class_router.message(F.text == BTN_MY_CLASS)
async def my_class_handler(message: Message, state: FSMContext) -> None:
    await reset_screen(message.bot, message.chat.id, state)

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
        sent = await message.answer("Выберите класс для просмотра:", reply_markup=kb)
        await set_screen(state, sent.message_id)
        return

    teacher = get_teacher_by_telegram_id(user_id)
    if not teacher or not teacher.class_id:
        await message.answer("У вас не указан класс. Обратитесь к администратору.")
        return

    sent = await _show_absent_list(message, teacher.class_id, teacher.school_id, edit=False)
    if sent:
        await set_screen(state, sent.message_id)


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
    return teacher.school_id if teacher else get_default_school_id()


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


async def _show_absent_list(message: Message, class_id: int, school_id: int, edit: bool = False):
    today = date.today()
    session = get_class_session_today(class_id, today, school_id)
    absent = get_absent_students_today(class_id, today, school_id=school_id)

    classes = get_all_classes(school_id)
    class_obj = next((c for c in classes if c.id == class_id), None)
    class_name = class_obj.name if class_obj else "?"

    if session is None:
        text = f"📋 В классе {class_name} сегодня перекличка не проводилась."
        kb = InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]])
        return await _send_or_edit(message, text, kb, edit)

    if session["status"] == "active":
        text = f"⏳ В классе {class_name} перекличка ещё идёт. Дождитесь завершения."
        kb = InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]])
        return await _send_or_edit(message, text, kb, edit)

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
        return await _send_or_edit(message, text, kb, edit)

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

    return await _send_or_edit(message, text, kb, edit)


async def _send_or_edit(message, text, kb, edit):
    if edit:
        await message.edit_text(text, reply_markup=kb)
        return message
    return await message.answer(text, reply_markup=kb)


# ── Аналитика для классного руководителя ──────────────────────────────────

def _quarters_for_today(today: date) -> list[dict]:
    y, m = today.year, today.month
    start_year = y if m >= 9 else y - 1

    q_defs = [
        ("1-я четверть", date(start_year, 9, 1), date(start_year, 10, 31)),
        ("2-я четверть", date(start_year, 11, 1), date(start_year, 12, 31)),
        ("3-я четверть", date(start_year + 1, 1, 1), date(start_year + 1, 3, 31)),
        ("4-я четверть", date(start_year + 1, 4, 1), date(start_year + 1, 5, 31)),
    ]

    result = []
    for label, d_from, d_to in q_defs:
        if d_from <= today:
            result.append({
                "label": f"{label} {start_year}-{start_year + 1}",
                "short_label": label,
                "date_from": d_from,
                "date_to": d_to,
            })

    if m == 9:
        prev = start_year - 1
        result.insert(0, {
            "label": f"4-я четверть {prev}-{prev + 1}",
            "short_label": "4-я четверть",
            "date_from": date(prev + 1, 4, 1),
            "date_to": date(prev + 1, 5, 31),
        })

    return list(reversed(result))


def _find_quarter(date_from: date, date_to: date) -> dict | None:
    for q in _quarters_for_today(date.today()):
        if q["date_from"] == date_from and q["date_to"] == date_to:
            return q
    return None


async def _show_analytics_summary(target, class_id: int, school_id: int,
                                  quarter: dict, edit: bool = False):
    data = get_class_analytics(class_id, school_id, quarter["date_from"], quarter["date_to"])
    label = quarter["label"]

    if data["total_absences"] == 0:
        text = f"📊 {label}\n\nПропусков нет."
        kb = InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]])
        return await _send_or_edit(target, text, kb, edit)

    lines = [f"📊 {label}", f"Всего пропусков: {data['total_absences']}", ""]

    lines.append("🏆 Топ по пропускам:")
    for i, s in enumerate(data["top_students"], 1):
        lines.append(f"{i}. {s['name']} — {s['total']}")

    lines.append("")
    lines.append("📌 Причины:")
    total = data["total_absences"]
    for reason, cnt in sorted(data["by_reason"].items(), key=lambda x: -x[1]):
        pct = round(cnt / total * 100)
        lines.append(f"{reason} — {cnt} ({pct}%)")

    cb_suffix = f"{quarter['date_from'].isoformat()}:{quarter['date_to'].isoformat()}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Все ученики", callback_data=f"an:s:{cb_suffix}")],
        [back_to_menu_btn()],
    ])
    return await _send_or_edit(target, "\n".join(lines), kb, edit)


async def _show_analytics_students(target, class_id: int, school_id: int,
                                   quarter: dict, edit: bool = False):
    data = get_class_analytics(class_id, school_id, quarter["date_from"], quarter["date_to"])
    label = quarter["label"]

    with_abs = [s for s in data["students"] if s["total"] > 0]
    without_abs = [s for s in data["students"] if s["total"] == 0]

    lines = [f"📋 Все ученики — {label}", ""]

    if with_abs:
        for s in with_abs:
            parts = []
            for reason, cnt in sorted(s["by_reason"].items(), key=lambda x: -x[1]):
                icon = reason.split(" ")[0]
                parts.append(f"{icon}{cnt}")
            lines.append(f"• {s['name']} — {s['total']} ({', '.join(parts)})")
    else:
        lines.append("Пропусков нет ни у кого.")

    if without_abs:
        lines.append("")
        names = ", ".join(s["name"] for s in without_abs)
        lines.append(f"✅ Без пропусков ({len(without_abs)}): {names}")

    cb_suffix = f"{quarter['date_from'].isoformat()}:{quarter['date_to'].isoformat()}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ К сводке", callback_data=f"an:q:{cb_suffix}")],
        [back_to_menu_btn()],
    ])
    return await _send_or_edit(target, "\n".join(lines), kb, edit)


@my_class_router.message(F.text == BTN_ANALYTICS)
async def my_class_analytics(message: Message, state: FSMContext) -> None:
    await reset_screen(message.bot, message.chat.id, state)

    user_id = message.from_user.id
    if not check_access(user_id, [Role.CLASS_TEACHER]):
        await message.answer("У вас нет закреплённого класса.")
        return

    if is_admin(user_id):
        await message.answer("Аналитика доступна только классным руководителям.")
        return

    teacher = get_teacher_by_telegram_id(user_id)
    if not teacher or not teacher.class_id:
        await message.answer("У вас не указан класс. Обратитесь к администратору.")
        return

    quarters = _quarters_for_today(date.today())
    quarters = get_class_quarters_with_data(teacher.class_id, teacher.school_id, quarters)

    with_data = [q for q in quarters if q["total_absences"] > 0]
    if not with_data:
        sent = await message.answer(
            "📊 Аналитика\n\nПока нет данных о перекличках за текущий учебный год."
        )
        await set_screen(state, sent.message_id)
        return

    if len(with_data) == 1:
        sent = await _show_analytics_summary(
            message, teacher.class_id, teacher.school_id, with_data[0],
        )
        if sent:
            await set_screen(state, sent.message_id)
        return

    buttons = []
    for q in quarters:
        if q["total_absences"] > 0:
            text = f"{q['short_label']} ({q['total_absences']})"
        else:
            text = f"{q['short_label']} — нет данных"
        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"an:q:{q['date_from'].isoformat()}:{q['date_to'].isoformat()}",
        )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons + [[back_to_menu_btn()]])
    sent = await message.answer("📊 Выберите четверть:", reply_markup=kb)
    await set_screen(state, sent.message_id)


@my_class_router.callback_query(F.data.startswith("an:q:"))
async def analytics_quarter(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    if not check_access(user_id, [Role.CLASS_TEACHER]):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    if is_admin(user_id):
        await callback.answer("Только для классных руководителей.", show_alert=True)
        return

    teacher = get_teacher_by_telegram_id(user_id)
    if not teacher or not teacher.class_id:
        await callback.answer("У вас нет класса.", show_alert=True)
        return

    parts = callback.data.split(":")
    try:
        d_from = date.fromisoformat(parts[2])
        d_to = date.fromisoformat(parts[3])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных.", show_alert=True)
        return

    quarter = _find_quarter(d_from, d_to)
    if not quarter:
        await callback.answer("Четверть не найдена.", show_alert=True)
        return

    await _show_analytics_summary(
        callback.message, teacher.class_id, teacher.school_id, quarter, edit=True,
    )
    await callback.answer()


@my_class_router.callback_query(F.data.startswith("an:s:"))
async def analytics_students(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    if not check_access(user_id, [Role.CLASS_TEACHER]):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    if is_admin(user_id):
        await callback.answer("Только для классных руководителей.", show_alert=True)
        return

    teacher = get_teacher_by_telegram_id(user_id)
    if not teacher or not teacher.class_id:
        await callback.answer("У вас нет класса.", show_alert=True)
        return

    parts = callback.data.split(":")
    try:
        d_from = date.fromisoformat(parts[2])
        d_to = date.fromisoformat(parts[3])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных.", show_alert=True)
        return

    quarter = _find_quarter(d_from, d_to)
    if not quarter:
        await callback.answer("Четверть не найдена.", show_alert=True)
        return

    await _show_analytics_students(
        callback.message, teacher.class_id, teacher.school_id, quarter, edit=True,
    )
    await callback.answer()


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