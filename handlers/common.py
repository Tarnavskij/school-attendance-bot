# handlers/common.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from core.keyboards import build_menu_keyboard, start_kb, access_request_kb, BTN_MENU
from core.roles import is_admin, Role
from repositories import get_teacher_by_telegram_id

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
        if edit:
            # edit_text не меняет reply_markup — отправляем новое сообщение
            await target.answer(
                "Вы не зарегистрированы. Нажмите кнопку, чтобы запросить доступ.",
                reply_markup=access_request_kb,
            )
        else:
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
async def cmd_start(message: Message) -> None:
    await show_menu_for_user(message, message.from_user.id)


@common_router.message(F.text == BTN_MENU)
@common_router.message(Command("menu"))
async def show_menu(message: Message) -> None:
    await show_menu_for_user(message, message.from_user.id)


@common_router.callback_query(F.data == "nav:menu")
async def nav_to_menu(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await show_menu_for_user(callback.message, callback.from_user.id)
    await callback.answer()


@common_router.message()
async def fallback_any_message(message: Message) -> None:
    """
    Ловит любое сообщение, не обработанное другими хендлерами.
    Показывает правильное меню для роли — решает проблему после смены роли.
    ВАЖНО: этот роутер должен быть зарегистрирован последним в bot.py.
    """
    await show_menu_for_user(message, message.from_user.id)