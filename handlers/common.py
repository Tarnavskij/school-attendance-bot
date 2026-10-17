# handlers/common.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from core.keyboards import build_menu_keyboard, start_kb, access_request_kb, BTN_MENU
from core.roles import is_admin, Role
from repositories import get_teacher_by_telegram_id
from helpers.ui import reset_screen

common_router = Router()


async def show_menu_for_user(target, user_id: int, edit: bool = False) -> None:
    """
    Единая точка показа меню — используется из /start, /menu, BTN_MENU
    и как fallback при любом непонятном взаимодействии.
    """
    if is_admin(user_id):
        kb = build_menu_keyboard(user_id)
        text = "Выберите действие:"
        if edit:
            await target.edit_text(text, reply_markup=kb)
        else:
            await target.answer(text, reply_markup=kb)
        return

    teacher = get_teacher_by_telegram_id(user_id)
    if not teacher:
        await target.answer(
            "Вы не зарегистрированы. Нажмите кнопку, чтобы запросить доступ.",
            reply_markup=access_request_kb,
        )
        return

    kb = build_menu_keyboard(user_id)
    text = "Выберите действие:"
    if edit:
        await target.edit_text(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


@common_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await reset_screen(message.bot, message.chat.id, state)
    await show_menu_for_user(message, message.from_user.id)


@common_router.message(F.text == BTN_MENU)
@common_router.message(Command("menu"))
async def show_menu(message: Message, state: FSMContext) -> None:
    await reset_screen(message.bot, message.chat.id, state)
    await show_menu_for_user(message, message.from_user.id)


@common_router.callback_query(F.data == "nav:menu")
async def nav_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_text(
            "Выберите действие:",
            reply_markup=build_menu_keyboard(callback.from_user.id),
        )
    except TelegramBadRequest:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
    await callback.answer()


@common_router.message()
async def fallback_any_message(message: Message, state: FSMContext) -> None:
    await reset_screen(message.bot, message.chat.id, state)
    await show_menu_for_user(message, message.from_user.id)