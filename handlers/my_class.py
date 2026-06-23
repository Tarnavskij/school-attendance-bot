# handlers/my_class.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import date

from repositories import get_teacher_by_telegram_id, get_all_classes, get_absent_students_today, set_absence_reason
from core.keyboards import BTN_MY_CLASS, build_menu_keyboard, back_to_menu_btn
from core.roles import check_access, is_admin, Role
from core.constants import ABSENCE_REASONS

my_class_router = Router()


@my_class_router.message(F.text == BTN_MY_CLASS)
async def my_class_handler(message: Message) -> None:
    user_id = message.from_user.id
    if not check_access(user_id, [Role.CLASS_TEACHER]):
        await message.answer("У вас нет закреплённого класса.")
        return

    if is_admin(user_id):
        classes = get_all_classes()
        if not classes:
            await message.answer("Нет доступных классов.")
            return
        # Строим сетку по 2 кнопки в ряд
        buttons = [InlineKeyboardButton(text=c.name, callback_data=f"mc:view:{c.id}") for c in classes]
        rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        rows.append([back_to_menu_btn()])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await message.answer("Выберите класс для просмотра:", reply_markup=kb)
        return

    teacher = get_teacher_by_telegram_id(user_id)
    if not teacher or not teacher.class_id:
        await message.answer("У вас не указан класс. Обратитесь к администратору.")
        return

    await _show_absent_list(message, teacher.class_id, edit=False)


@my_class_router.callback_query(F.data.startswith("mc:view:"))
async def view_class(callback: CallbackQuery) -> None:
    if not check_access(callback.from_user.id, [Role.CLASS_TEACHER]):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    class_id = int(callback.data.split(":")[-1])
    await _show_absent_list(callback.message, class_id, edit=True)
    await callback.answer()


@my_class_router.callback_query(F.data.startswith("mc:reason_menu:"))
async def show_reason_menu(callback: CallbackQuery) -> None:
    if not check_access(callback.from_user.id, [Role.CLASS_TEACHER]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    _, _, student_id_str, class_id_str = callback.data.split(":")
    student_id = int(student_id_str)
    class_id = int(class_id_str)

    absent = get_absent_students_today(class_id, date.today())
    student_info = absent.get(student_id)
    student_name = student_info["name"] if student_info else f"ID {student_id}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        *[
            [InlineKeyboardButton(text=r, callback_data=f"mc:reason:{student_id}:{class_id}:{i}")]
            for i, r in enumerate(ABSENCE_REASONS)
        ],
        [InlineKeyboardButton(text="↩️ Назад", callback_data=f"mc:view:{class_id}")],
    ])
    await callback.message.edit_text(
        f"Выберите причину отсутствия для {student_name}:",
        reply_markup=kb,
    )
    await callback.answer()


@my_class_router.callback_query(F.data.startswith("mc:reason:"))
async def apply_reason(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    student_id = int(parts[2])
    class_id = int(parts[3])
    reason_idx = int(parts[4])
    reason = ABSENCE_REASONS[reason_idx]

    set_absence_reason(student_id, class_id, date.today(), reason)
    await callback.answer("Причина сохранена.")
    # Редактируем текущее сообщение, возвращая список отсутствующих
    await _show_absent_list(callback.message, class_id, edit=True)


async def _show_absent_list(message: Message, class_id: int, edit: bool = False) -> None:
    """Показывает (или редактирует) список отсутствующих с кнопками."""
    today = date.today()
    absent = get_absent_students_today(class_id, today)

    classes = get_all_classes()
    class_obj = next((c for c in classes if c.id == class_id), None)
    class_name = class_obj.name if class_obj else "?"

    if not absent:
        kb = InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]])
        text = f"📋 В классе {class_name} сегодня отсутствующих нет."
    else:
        rows = []
        for student_id, info in absent.items():
            label = info["name"]
            if info["reason"]:
                label += f" ({info['reason']})"
            rows.append([InlineKeyboardButton(
                text=label,
                callback_data=f"mc:reason_menu:{student_id}:{class_id}",
            )])
        rows.append([back_to_menu_btn()])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        text = f"📋 Отсутствующие в классе {class_name} (нажмите для указания причины):"

    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)