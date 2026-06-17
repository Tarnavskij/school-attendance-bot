# handlers/common.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from core.keyboards import build_menu_keyboard, start_kb, access_request_kb, BTN_MENU
from core.roles import is_admin
from repositories import get_teacher_by_telegram_id

common_router = Router()


@common_router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer("Добро пожаловать! Нажмите «Меню».", reply_markup=start_kb)


@common_router.message(F.text == BTN_MENU)
@common_router.message(Command("menu"))
async def show_menu(message: Message) -> None:
    user_id = message.from_user.id

    if is_admin(user_id):
        await message.answer("Выберите действие:", reply_markup=build_menu_keyboard(user_id))
        return

    teacher = get_teacher_by_telegram_id(user_id)
    if not teacher:
        await message.answer(
            "Вы не зарегистрированы. Нажмите кнопку, чтобы запросить доступ.",
            reply_markup=access_request_kb,
        )
        return

    kb = build_menu_keyboard(user_id)
    if kb.keyboard:
        await message.answer("Выберите действие:", reply_markup=kb)
    else:
        await message.answer("У вас нет доступных действий.")


@common_router.callback_query(F.data == "nav:menu")
async def nav_to_menu(callback: CallbackQuery) -> None:
    await callback.message.delete()
    kb = build_menu_keyboard(callback.from_user.id)
    await callback.message.answer("Выберите действие:", reply_markup=kb)
    await callback.answer()