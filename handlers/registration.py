# handlers/registration.py
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from repositories import get_teacher_by_telegram_id, get_all_classes, get_all_schools
from core.keyboards import BTN_REQUEST_ACCESS
from config import ADMIN_TELEGRAM_ID
from core.roles import ROLE_LABELS, Role
from database import SessionLocal, RegistrationRequest

registration_router = Router()


class RegistrationStates(StatesGroup):
    waiting_name = State()
    waiting_surname = State()
    choosing_role = State()
    choosing_school = State()       # ← новое состояние
    choosing_class = State()


@registration_router.message(F.text == BTN_REQUEST_ACCESS)
async def start_registration(message: Message, state: FSMContext) -> None:
    if get_teacher_by_telegram_id(message.from_user.id):
        await message.answer("Вы уже зарегистрированы. Нажмите /menu.")
        return
    await state.set_state(RegistrationStates.waiting_name)
    await message.answer("Введите ваше имя:")


@registration_router.message(RegistrationStates.waiting_name)
async def process_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Имя не может быть пустым. Введите имя:")
        return
    await state.update_data(name=name)
    await state.set_state(RegistrationStates.waiting_surname)
    await message.answer("Введите вашу фамилию:")


@registration_router.message(RegistrationStates.waiting_surname)
async def process_surname(message: Message, state: FSMContext) -> None:
    surname = message.text.strip()
    if not surname:
        await message.answer("Фамилия не может быть пустой. Введите фамилию:")
        return
    await state.update_data(surname=surname)

    # Показываем выбор роли
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🏫 Классный руководитель", callback_data="reg:role:class_teacher")],
        [InlineKeyboardButton(text="🧑‍🏫 Учитель-предметник", callback_data="reg:role:subject_teacher")],
        [InlineKeyboardButton(text="🗂 Секретарь", callback_data="reg:role:secretary")],
    ])
    await state.set_state(RegistrationStates.choosing_role)
    await message.answer("Выберите вашу роль:", reply_markup=kb)


@registration_router.callback_query(RegistrationStates.choosing_role, F.data.startswith("reg:role:"))
async def role_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    role = callback.data.split(":")[-1]
    await state.update_data(role=role)

    # Проверяем количество школ
    schools = get_all_schools()
    if len(schools) > 1:
        # Если школ несколько — предлагаем выбрать
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=s['name'], callback_data=f"reg:school:{s['id']}:{s['name']}")]
            for s in schools
        ])
        await state.set_state(RegistrationStates.choosing_school)
        await callback.message.edit_text("Выберите вашу школу:", reply_markup=kb)
    else:
        # Школа одна — запоминаем её id и переходим к следующему шагу
        school_id = schools[0]['id'] if schools else 1
        await state.update_data(school_id=school_id)
        await _proceed_after_school(callback, state, role)


async def _proceed_after_school(callback: CallbackQuery, state: FSMContext, role: str) -> None:
    """Действия после определения школы (или если она единственная)."""
    if role == Role.CLASS_TEACHER:
        classes = get_all_classes()
        if not classes:
            await callback.message.edit_text("Нет доступных классов. Обратитесь к администратору.")
            await state.clear()
            await callback.answer()
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=c.name, callback_data=f"reg:class:{c.id}:{c.name}")]
            for c in classes
        ])
        await state.set_state(RegistrationStates.choosing_class)
        await callback.message.edit_text("Выберите ваш класс:", reply_markup=kb)
    else:
        data = await state.get_data()
        school_id = data.get("school_id", 1)
        await _save_and_notify(callback.from_user.id, state, callback.bot, class_name=None, school_id=school_id)
        await callback.message.edit_text(
            "✅ Заявка отправлена администратору. Ожидайте подтверждения.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")]
            ])
        )
        await state.clear()
    await callback.answer()


@registration_router.callback_query(RegistrationStates.choosing_school, F.data.startswith("reg:school:"))
async def school_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    school_id = int(parts[2])
    # school_name = parts[3]  # не понадобится, т.к. у нас есть id
    await state.update_data(school_id=school_id)

    data = await state.get_data()
    role = data.get("role", Role.SUBJECT_TEACHER)
    await _proceed_after_school(callback, state, role)


@registration_router.callback_query(RegistrationStates.choosing_class, F.data.startswith("reg:class:"))
async def class_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    class_name = parts[-1]
    data = await state.get_data()
    school_id = data.get("school_id", 1)
    await _save_and_notify(callback.from_user.id, state, callback.bot, class_name=class_name, school_id=school_id)
    await callback.message.edit_text(
        "✅ Заявка отправлена администратору. Ожидайте подтверждения.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")]
        ])
    )
    await state.clear()
    await callback.answer()


async def _save_and_notify(user_id: int, state: FSMContext, bot: Bot, class_name: str | None, school_id: int) -> None:
    data = await state.get_data()
    name = f"{data.get('name', '')} {data.get('surname', '')}".strip()
    role = data.get("role", Role.SUBJECT_TEACHER)

    # Получаем название школы для уведомления
    schools = get_all_schools()
    school_name = next((s['name'] for s in schools if s['id'] == school_id), "Неизвестная школа")

    db = SessionLocal()
    req = RegistrationRequest(
        telegram_id=user_id,
        name=name,
        role=role,
        class_name=class_name,
        status="pending",
        school_id=school_id,          # ← теперь заполняем школу
    )
    db.add(req)
    db.commit()
    db.close()

    text = (
        f"📩 Новая заявка на доступ!\n"
        f"Имя: {name}\n"
        f"Telegram ID: {user_id}\n"
        f"Роль: {ROLE_LABELS.get(role, role)}\n"
        f"Класс: {class_name or 'не выбран'}\n"
        f"🏫 Школа: {school_name}\n\n"
        f"Одобрите или отклоните в веб-панели."
    )
    await bot.send_message(ADMIN_TELEGRAM_ID, text)