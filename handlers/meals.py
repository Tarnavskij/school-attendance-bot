# handlers/meals.py
from datetime import date
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from core.keyboards import BTN_MEAL, back_to_menu_btn
from core.roles import check_access, Role, is_admin
from repositories import (
    get_teacher_by_telegram_id,
    get_or_create_meal_request,
    save_meal_request,
    update_student_meal_type,
    MealItemDTO,
    get_chef_telegram_ids,
    get_class_meal_summary,
    is_meal_request_exists,
)

meals_router = Router()


def _meal_type_emoji(meal_type: str) -> str:
    return "💰" if meal_type == "paid" else "🆓"


async def _notify_chefs_for_class(bot: Bot, class_id: int, school_id: int):
    """Отправляет сообщение всем шеф-поварам школы об обновлении заявки класса."""
    chef_ids = get_chef_telegram_ids(school_id)
    if not chef_ids:
        return
    summary = get_class_meal_summary(class_id, school_id)
    for chef_id in chef_ids:
        try:
            await bot.send_message(chef_id, summary)
        except Exception:
            pass


@meals_router.message(F.text == BTN_MEAL)
async def meal_menu(message: Message):
    user_id = message.from_user.id
    # Только классный руководитель (или админ) может работать с заявками
    if not check_access(user_id, [Role.CLASS_TEACHER]):
        return  # шеф-повара и другие пропускаем молча

    teacher = get_teacher_by_telegram_id(user_id)
    if is_admin(user_id):
        await message.answer("Выберите класс (функция для администратора пока не реализована).")
        return

    if not teacher or not teacher.class_id:
        await message.answer("У вас не указан класс. Обратитесь к администратору.")
        return

    await _show_meal_markup(message, teacher.class_id, teacher.id, teacher.school_id, edit=False)


async def _show_meal_markup(target, class_id: int, teacher_id: int, school_id: int, edit: bool = False):
    """Показывает список учеников с кнопками 'ест/не ест' и сменой типа питания."""
    request = get_or_create_meal_request(class_id, school_id=school_id)
    if not request.items:
        text = "В классе нет учеников."
        if edit:
            await target.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]]))
        else:
            await target.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]]))
        return

    kb_rows = []
    for item in request.items:
        eating_icon = "✅" if item.is_eating else "❌"
        type_icon = _meal_type_emoji(item.meal_type)
        toggle_btn = InlineKeyboardButton(
            text=f"{eating_icon} {item.name} ({type_icon})",
            callback_data=f"meal:toggle:{item.student_id}"
        )
        type_btn = InlineKeyboardButton(
            text=type_icon,
            callback_data=f"meal:type:{item.student_id}"
        )
        kb_rows.append([toggle_btn, type_btn])

    kb_rows.append([
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="meal:submit"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="meal:cancel"),
    ])

    text = f"🍽️ Питание на {date.today().strftime('%d.%m.%Y')}\nКласс: {request.class_name}\n✅ — ест, ❌ — не ест"

    if edit:
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    else:
        await target.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))


meal_states: dict[int, dict] = {}

def _get_state(chat_id: int) -> dict:
    if chat_id not in meal_states:
        meal_states[chat_id] = {}
    return meal_states[chat_id]


@meals_router.callback_query(F.data.startswith("meal:toggle:"))
async def toggle_eating(callback: CallbackQuery):
    student_id = int(callback.data.split(":")[-1])
    state = _get_state(callback.message.chat.id)
    if 'items' not in state:
        teacher = get_teacher_by_telegram_id(callback.from_user.id)
        if not teacher or not teacher.class_id:
            await callback.answer("Ошибка: нет класса.")
            return
        request = get_or_create_meal_request(teacher.class_id, school_id=teacher.school_id)
        state['items'] = {item.student_id: item for item in request.items}
        state['class_id'] = teacher.class_id
        state['teacher_id'] = teacher.id
        state['school_id'] = teacher.school_id

    item = state['items'].get(student_id)
    if item:
        item.is_eating = not item.is_eating
        await _redraw_meal_message(callback.message, state)
    await callback.answer()


@meals_router.callback_query(F.data.startswith("meal:type:"))
async def change_meal_type(callback: CallbackQuery):
    student_id = int(callback.data.split(":")[-1])
    state = _get_state(callback.message.chat.id)
    if 'items' not in state:
        teacher = get_teacher_by_telegram_id(callback.from_user.id)
        if not teacher or not teacher.class_id:
            await callback.answer("Ошибка: нет класса.")
            return
        request = get_or_create_meal_request(teacher.class_id, school_id=teacher.school_id)
        state['items'] = {item.student_id: item for item in request.items}
        state['class_id'] = teacher.class_id
        state['teacher_id'] = teacher.id
        state['school_id'] = teacher.school_id

    item = state['items'].get(student_id)
    if item:
        new_type = "free" if item.meal_type == "paid" else "paid"
        item.meal_type = new_type
        update_student_meal_type(student_id, new_type)
        await _redraw_meal_message(callback.message, state)
    await callback.answer()


async def _redraw_meal_message(message, state: dict):
    """Перерисовывает сообщение с текущим состоянием."""
    items = state['items']
    kb_rows = []
    for item in items.values():
        eating_icon = "✅" if item.is_eating else "❌"
        type_icon = _meal_type_emoji(item.meal_type)
        toggle_btn = InlineKeyboardButton(
            text=f"{eating_icon} {item.name} ({type_icon})",
            callback_data=f"meal:toggle:{item.student_id}"
        )
        type_btn = InlineKeyboardButton(
            text=type_icon,
            callback_data=f"meal:type:{item.student_id}"
        )
        kb_rows.append([toggle_btn, type_btn])
    kb_rows.append([
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="meal:submit"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="meal:cancel"),
    ])
    try:
        await message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    except Exception:
        pass


@meals_router.callback_query(F.data == "meal:submit")
async def submit_meal(callback: CallbackQuery):
    state = _get_state(callback.message.chat.id)
    if 'items' not in state:
        await callback.answer("Нет изменений.")
        return

    items = list(state['items'].values())
    class_id = state['class_id']
    teacher_id = state['teacher_id']
    school_id = state.get('school_id')
    if not school_id:
        teacher = get_teacher_by_telegram_id(callback.from_user.id)
        school_id = teacher.school_id if teacher else None
        if not school_id:
            await callback.answer("Ошибка: школа не определена.")
            return

    existed_before = is_meal_request_exists(class_id, date.today(), school_id)
    save_meal_request(class_id, teacher_id, items, school_id=school_id)

    if existed_before:
        await _notify_chefs_for_class(callback.bot, class_id, school_id)

    meal_states.pop(callback.message.chat.id, None)
    await callback.message.edit_text("✅ Заявка на питание отправлена.", reply_markup=None)
    await callback.answer("Отправлено!")


@meals_router.callback_query(F.data == "meal:cancel")
async def cancel_meal(callback: CallbackQuery):
    meal_states.pop(callback.message.chat.id, None)
    await callback.message.edit_text("Питание отменено.", reply_markup=None)
    await callback.answer()