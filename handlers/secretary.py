# handlers/secretary.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from datetime import date

from helpers.quarters import get_available_quarters
from core.keyboards import BTN_EXPORT_ABSENCES, BTN_ROLL_STATUS
from repositories import (
    is_school_done_today,
    get_absence_reason_counts,
    get_teacher_by_telegram_id,
    get_default_school_id,
    get_all_classes,
    get_absences_export_data
)
from helpers.excel_export import generate_absences_excel
from core.roles import check_access, Role
from core.constants import ABSENCE_REASONS

secretary_router = Router()


@secretary_router.message(F.text == BTN_ROLL_STATUS)
async def roll_status(message: Message) -> None:
    if not check_access(message.from_user.id, [Role.SECRETARY]):
        await message.answer("Нет доступа.")
        return

    teacher = get_teacher_by_telegram_id(message.from_user.id)
    school_id = teacher.school_id if teacher else get_default_school_id()

    today = date.today()

    if not is_school_done_today(today, school_id):
        await message.answer("⏳ Перекличка в процессе.")
        return

    counts = get_absence_reason_counts(today, school_id)
    total = counts.get("__total__", 0)

    lines = ["✅ Перекличка готова.", f"\nВсего отсутствует: {total}"]
    for reason in ABSENCE_REASONS:
        lines.append(f"{reason}: {counts.get(reason, 0)}")

    await message.answer("\n".join(lines))


# ДОБАВЛЕНА ПРОВЕРКА РОЛИ В ФИЛЬТР
@secretary_router.message(F.text == BTN_EXPORT_ABSENCES, lambda msg: check_access(msg.from_user.id, [Role.SECRETARY]))
async def export_absences_secretary(message: Message):
    quarters = get_available_quarters(date.today())
    buttons = []
    for q in quarters:
        buttons.append([InlineKeyboardButton(
            text=q["label"],
            callback_data=f"exp_q:{q['date_from'].isoformat()}:{q['date_to'].isoformat()}"
        )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("📥 Выберите период для экспорта:", reply_markup=kb)


@secretary_router.callback_query(F.data.startswith("exp_q:"), lambda cb: check_access(cb.from_user.id, [Role.SECRETARY]))
async def export_choose_class(callback: CallbackQuery):
    _, d_from_str, d_to_str = callback.data.split(":")
    d_from = date.fromisoformat(d_from_str)
    d_to = date.fromisoformat(d_to_str)

    q_info = next((q for q in get_available_quarters(date.today()) if q["date_from"] == d_from), None)
    q_label = q_info["label"] if q_info else "Период"

    teacher = get_teacher_by_telegram_id(callback.from_user.id)
    school_id = teacher.school_id if teacher else 1
    classes = get_all_classes(school_id)

    # Группировка по параллелям (5, 6, 7...)
    groups: dict[int, list] = {}
    for c in classes:
        grade = c.grade or 0
        groups.setdefault(grade, []).append(c)

    buttons = []
    for grade in sorted(groups.keys()):
        row = []
        for c in groups[grade]:
            row.append(InlineKeyboardButton(
                text=c.name,
                callback_data=f"exp_c:{d_from_str}:{d_to_str}:{c.id}"
            ))
        buttons.append(row)

    # Дополнительные кнопки
    buttons.append([InlineKeyboardButton(
        text="📦 Все классы",
        callback_data=f"exp_c:{d_from_str}:{d_to_str}:0"
    )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад к четвертям", callback_data="exp_back_q")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(f"📥 {q_label}\nВыберите класс:", reply_markup=kb)
    await callback.answer()


# Добавь этот хендлер ниже
@secretary_router.callback_query(F.data == "exp_back_q", lambda cb: check_access(cb.from_user.id, [Role.SECRETARY]))
async def export_back_quarters(callback: CallbackQuery):
    quarters = get_available_quarters(date.today())
    buttons = []
    for q in quarters:
        buttons.append([InlineKeyboardButton(
            text=q["label"],
            callback_data=f"exp_q:{q['date_from'].isoformat()}:{q['date_to'].isoformat()}"
        )])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("📥 Выберите период для экспорта:", reply_markup=kb)
    await callback.answer()


@secretary_router.callback_query(F.data.startswith("exp_c:"), lambda cb: check_access(cb.from_user.id, [Role.SECRETARY]))
async def export_generate_file(callback: CallbackQuery):
    _, d_from_str, d_to_str, class_id_str = callback.data.split(":")
    d_from = date.fromisoformat(d_from_str)
    d_to = date.fromisoformat(d_to_str)
    class_id = int(class_id_str)

    teacher = get_teacher_by_telegram_id(callback.from_user.id)
    school_id = teacher.school_id if teacher else 1

    q_info = next((q for q in get_available_quarters(date.today()) if q["date_from"] == d_from), None)
    q_label = q_info["short_label"] if q_info else "Период"

    class_label = "Все классы"
    if class_id != 0:
        classes = get_all_classes(school_id)
        c_obj = next((c for c in classes if c.id == class_id), None)
        if c_obj:
            class_label = c_obj.name

    await callback.message.edit_text(f"⏳ Формирую отчет за {q_label} ({class_label})...")

    data = get_absences_export_data(school_id, class_id if class_id != 0 else None, d_from, d_to)
    if not data:
        await callback.message.edit_text("❌ Нет данных для отчета за этот период.")
        return

    title_info = f"{q_label} — {class_label}"
    file_bytes = generate_absences_excel(data, title_info=title_info)

    safe_filename = title_info.replace(" ", "_").replace("—", "").replace("-", "")
    filename = f"absences_{safe_filename}.xlsx"

    document = BufferedInputFile(file_bytes, filename=filename)
    await callback.message.edit_text("✅ Отчет сформирован!")
    await callback.message.answer_document(document, caption=f"📥 Отчет по пропускам: {title_info}")
    await callback.answer()