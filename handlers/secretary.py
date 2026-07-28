# handlers/secretary.py
from aiogram import Router, F
from aiogram.types import Message
from datetime import date

from repositories import is_school_done_today, get_absence_reason_counts, get_teacher_by_telegram_id
from core.keyboards import BTN_ROLL_STATUS
from core.roles import check_access, Role
from core.constants import ABSENCE_REASONS
from config import DEFAULT_SCHOOL_ID

secretary_router = Router()


@secretary_router.message(F.text == BTN_ROLL_STATUS)
async def roll_status(message: Message) -> None:
    if not check_access(message.from_user.id, [Role.SECRETARY]):
        await message.answer("Нет доступа.")
        return

    # Получаем school_id из профиля секретаря
    teacher = get_teacher_by_telegram_id(message.from_user.id)
    school_id = teacher.school_id if teacher else DEFAULT_SCHOOL_ID

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