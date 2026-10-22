# handlers/secretary.py
from aiogram import Router, F
from aiogram.types import Message
from datetime import date

from aiogram.types import BufferedInputFile
from core.keyboards import BTN_EXPORT_ABSENCES
from repositories import get_absences_export_data
from helpers.excel_export import generate_absences_excel

from repositories import (
    is_school_done_today,
    get_absence_reason_counts,
    get_teacher_by_telegram_id,
    get_default_school_id,  # <-- добавили импорт
)
from core.keyboards import BTN_ROLL_STATUS
from core.roles import check_access, Role
from core.constants import ABSENCE_REASONS
# from config import DEFAULT_SCHOOL_ID  # <-- убрали импорт

secretary_router = Router()


@secretary_router.message(F.text == BTN_ROLL_STATUS)
async def roll_status(message: Message) -> None:
    if not check_access(message.from_user.id, [Role.SECRETARY]):
        await message.answer("Нет доступа.")
        return

    # Получаем school_id из профиля секретаря
    teacher = get_teacher_by_telegram_id(message.from_user.id)
    school_id = teacher.school_id if teacher else get_default_school_id()  # <-- заменили

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


@secretary_router.message(F.text == BTN_EXPORT_ABSENCES)
async def export_absences_secretary(message: Message):
    if not check_access(message.from_user.id, [Role.SECRETARY]):
        await message.answer("Нет доступа.")
        return

    teacher = get_teacher_by_telegram_id(message.from_user.id)
    school_id = teacher.school_id if teacher else 1
    data = get_absences_export_data(school_id)
    if not data:
        await message.answer("Нет данных для отчета.")
        return

    file_bytes = generate_absences_excel(data)
    document = BufferedInputFile(file_bytes, filename=f"absences_report.xlsx")
    await message.answer_document(document, caption="📥 Отчет по пропускам")