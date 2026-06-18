# handlers/secretary.py
from aiogram import Router, F
from aiogram.types import Message
from datetime import date

from repositories import is_school_done_today, get_absence_reason_counts
from core.keyboards import BTN_ROLL_STATUS
from core.roles import check_access, Role
from core.constants import ABSENCE_REASONS

secretary_router = Router()


@secretary_router.message(F.text == BTN_ROLL_STATUS)
async def roll_status(message: Message) -> None:
    if not check_access(message.from_user.id, [Role.SECRETARY]):
        await message.answer("Нет доступа.")
        return

    today = date.today()

    if not is_school_done_today(today):
        await message.answer("⏳ Перекличка в процессе.")
        return

    counts = get_absence_reason_counts(today)
    total = counts.get("__total__", 0)

    lines = ["✅ Перекличка готова.", f"\nВсего отсутствует: {total}"]
    for reason in ABSENCE_REASONS:
        lines.append(f"{reason}: {counts.get(reason, 0)}")

    await message.answer("\n".join(lines))