# handlers/meals.py
from datetime import date
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

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


# ── FSM Состояния ─────────────────────────────────────────────────────────────
class MealStates(StatesGroup):
    editing = State()


# ── Вспомогательные функции ───────────────────────────────────────────────────
def _meal_type_emoji(meal_type: str) -> str:
    return "💰" if meal_type == "paid" else "🆓"


async def _notify_chefs_with_summary(bot: Bot, school_id: int, summary_text: str) -> None:
    """Отправляет готовую сводку всем шеф-поварам школы."""
    chef_ids = get_chef_telegram_ids(school_id)
    if not chef_ids:
        return
    for chef_id in chef_ids:
        try:
            await bot.send_message(chef_id, summary_text)
        except Exception as e:
            from logger import get_logger
            get_logger(__name__).warning(f"Не удалось уведомить шеф-повара {chef_id}: {e}")


async def render_meal_keyboard(target: Message | CallbackQuery, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    items_dict = data.get("items", {})
    class_name = data.get("class_name", "Неизвестный класс")
    is_admin_mode = data.get("is_admin_mode", False)

    if not items_dict:
        text = "В классе нет учеников или данные не загружены."
        kb = InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]])
        if edit and isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=kb)
        else:
            await target.answer(text, reply_markup=kb)
        return

    kb_rows = []
    for item in items_dict.values():
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

    text = f"🍽️ Питание на {date.today().strftime('%d.%m.%Y')}\nКласс: {class_name}\n✅ — ест, ❌ — не ест"
    if is_admin_mode:
        text += "\n👑 Режим администратора"

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    if edit and isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


# ── Хендлеры ──────────────────────────────────────────────────────────────────
@meals_router.message(F.text == BTN_MEAL)
async def meal_menu(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not check_access(user_id, [Role.CLASS_TEACHER]):
        return

    if is_admin(user_id):
        await message.answer("Используйте кнопку 'Управление питанием' в меню администратора.")
        return

    teacher = get_teacher_by_telegram_id(user_id)
    if not teacher or not teacher.class_id:
        await message.answer("У вас не указан класс. Обратитесь к администратору.")
        return

    request = get_or_create_meal_request(teacher.class_id, school_id=teacher.school_id)
    items_dict = {item.student_id: item for item in request.items}

    await state.update_data(
        class_id=teacher.class_id,
        teacher_id=teacher.id,
        school_id=teacher.school_id,
        class_name=request.class_name,
        items=items_dict,
        is_admin_mode=False
    )
    await state.set_state(MealStates.editing)
    await render_meal_keyboard(message, state, edit=False)


@meals_router.callback_query(MealStates.editing, F.data.startswith("meal:toggle:"))
async def toggle_eating(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    items_dict = data.get("items", {})
    if student_id in items_dict:
        items_dict[student_id].is_eating = not items_dict[student_id].is_eating
        await state.update_data(items=items_dict)
    await render_meal_keyboard(callback, state, edit=True)
    await callback.answer()


@meals_router.callback_query(MealStates.editing, F.data.startswith("meal:type:"))
async def change_meal_type(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    items_dict = data.get("items", {})
    if student_id in items_dict:
        item = items_dict[student_id]
        new_type = "free" if item.meal_type == "paid" else "paid"
        item.meal_type = new_type
        update_student_meal_type(student_id, new_type)
        await state.update_data(items=items_dict)
    await render_meal_keyboard(callback, state, edit=True)
    await callback.answer()


@meals_router.callback_query(MealStates.editing, F.data == "meal:submit")
async def submit_meal(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    items_dict = data.get("items", {})
    if not items_dict:
        await callback.answer("Нет данных для отправки.", show_alert=True)
        return

    items_list = list(items_dict.values())
    class_id = data["class_id"]
    teacher_id = data.get("teacher_id")
    school_id = data["school_id"]
    is_admin_mode = data.get("is_admin_mode", False)

    existed_before = is_meal_request_exists(class_id, date.today(), school_id)
    save_meal_request(class_id, teacher_id, items_list, school_id=school_id)

    # Если заявка обновляется, уведомляем шеф-поваров с актуальными данными из items_list
    if existed_before and not is_admin_mode:
        total = len(items_list)
        paid = sum(1 for item in items_list if item.meal_type == "paid")
        free = total - paid
        class_name = data.get("class_name", "Класс")
        summary_text = f"🔄 Обновление питания для {class_name}: всего {total} (платно {paid}, бесплатно {free})"
        await _notify_chefs_with_summary(callback.bot, school_id, summary_text)

    notify = getattr(callback.bot, "notify_web", None)
    if notify:
        await notify("meals_update", {"school_id": school_id})

    await state.clear()
    await callback.message.edit_text("✅ Заявка на питание отправлена.", reply_markup=None)
    await callback.answer("Отправлено!")


@meals_router.callback_query(MealStates.editing, F.data == "meal:cancel")
async def cancel_meal(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Редактирование питания отменено.", reply_markup=None)
    await callback.answer()