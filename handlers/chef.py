# handlers/chef.py
from aiogram import Router, F
from aiogram.types import Message
from core.keyboards import BTN_CHEF_MEAL, BTN_CHEF_FREE
from core.roles import check_access, Role
from repositories import get_teacher_by_telegram_id, get_meal_summary, get_free_meals_report

chef_router = Router()


@chef_router.message(F.text == BTN_CHEF_MEAL)
async def chef_meal_summary(message: Message):
    user_id = message.from_user.id
    if not check_access(user_id, [Role.CHEF]):
        return  # пропускаем, если не шеф-повар
    chef = get_teacher_by_telegram_id(user_id)
    if not chef:
        return
    summary = get_meal_summary(chef.school_id)
    await message.answer(summary)


@chef_router.message(F.text == BTN_CHEF_FREE)
async def chef_free_meals(message: Message):
    user_id = message.from_user.id
    if not check_access(user_id, [Role.CHEF]):
        return
    chef = get_teacher_by_telegram_id(user_id)
    if not chef:
        return
    report = get_free_meals_report(chef.school_id)
    await message.answer(report)