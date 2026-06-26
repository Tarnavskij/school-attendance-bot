# handlers/registration.py
import re

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from repositories import (
    get_teacher_by_telegram_id,
    get_all_classes,
    get_all_schools,
    has_pending_request,
)
from core.keyboards import BTN_REQUEST_ACCESS, access_request_kb
from config import ADMIN_TELEGRAM_ID
from core.roles import ROLE_LABELS, Role
from database import SessionLocal, RegistrationRequest

registration_router = Router()

# ── Валидация имени/фамилии ───────────────────────────────────────────────────

_NAME_RE = re.compile(r"^[A-Za-zА-ЯЁа-яё][A-Za-zА-ЯЁа-яё'\-]{1,29}$")
_NAME_MIN = 2
_NAME_MAX = 30

_ERR_NAME = (
    "Пожалуйста, введите настоящее имя:\n"
    "• только буквы (русские или латинские), дефис и апостроф\n"
    "• от {min} до {max} символов\n"
    "• без цифр, пробелов, эмодзи и спецсимволов"
).format(min=_NAME_MIN, max=_NAME_MAX)

_ERR_SURNAME = (
    "Пожалуйста, введите настоящую фамилию:\n"
    "• только буквы (русские или латинские), дефис и апостроф\n"
    "• от {min} до {max} символов\n"
    "• без цифр, пробелов, эмодзи и спецсимволов"
).format(min=_NAME_MIN, max=_NAME_MAX)


def _validate_name_part(text: str) -> bool:
    """Возвращает True, если текст проходит валидацию имени/фамилии."""
    return bool(_NAME_RE.match(text))


# ── FSM ───────────────────────────────────────────────────────────────────────

class RegistrationStates(StatesGroup):
    waiting_name = State()
    waiting_surname = State()
    choosing_role = State()
    choosing_school = State()
    choosing_class = State()


# ── Отмена регистрации при /start или /menu ───────────────────────────────────

async def _cancel_registration(message: Message, state: FSMContext) -> None:
    """Сбрасывает FSM и сообщает пользователю об отмене."""
    await state.clear()
    await message.answer(
        "Регистрация отменена. Если захотите попробовать снова — нажмите кнопку ниже.",
        reply_markup=access_request_kb,
    )


@registration_router.message(RegistrationStates.waiting_name, Command("start", "menu"))
@registration_router.message(RegistrationStates.waiting_surname, Command("start", "menu"))
@registration_router.message(RegistrationStates.choosing_role, Command("start", "menu"))
async def cancel_on_command(message: Message, state: FSMContext) -> None:
    await _cancel_registration(message, state)


# Для шагов с выбором через inline-кнопки команды тоже должны отменять процесс.
# Поскольку choosing_school и choosing_class ожидают callback, а не текст,
# перехватываем любое текстовое сообщение в этих состояниях.
@registration_router.message(RegistrationStates.choosing_school)
@registration_router.message(RegistrationStates.choosing_class)
async def cancel_on_text_during_inline(message: Message, state: FSMContext) -> None:
    """Любой текст (включая команды) во время выбора школы/класса — отмена."""
    await _cancel_registration(message, state)


# ── Вход в регистрацию ────────────────────────────────────────────────────────

@registration_router.message(F.text == BTN_REQUEST_ACCESS)
async def start_registration(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id

    # Уже зарегистрирован и активен
    if get_teacher_by_telegram_id(user_id):
        await message.answer("Вы уже зарегистрированы. Нажмите /menu.")
        return

    # Незакрытая заявка существует — проверяем по всем школам (школа одна в 99% случаев)
    # и используем school_id=1 как дефолт, потому что на этом этапе школа ещё не выбрана.
    # Полная проверка по конкретной школе будет повторена перед сохранением.
    schools = get_all_schools()
    for school in schools:
        if has_pending_request(user_id, school["id"]):
            await message.answer(
                "Вы уже подали заявку и она ожидает рассмотрения. "
                "Как только администратор примет решение, вы получите доступ."
            )
            return

    # Сбрасываем возможное «зависшее» FSM-состояние от предыдущей попытки
    await state.clear()
    await state.set_state(RegistrationStates.waiting_name)
    await message.answer(
        "Шаг 1 из 3 — введите ваше <b>имя</b> (только буквы, от 2 до 30 символов).\n\n"
        "Чтобы отменить регистрацию в любой момент, нажмите /menu.",
        parse_mode="HTML",
    )


# ── Шаг 1: имя ───────────────────────────────────────────────────────────────

@registration_router.message(RegistrationStates.waiting_name)
async def process_name(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()

    if not _validate_name_part(raw):
        await message.answer(_ERR_NAME)
        return

    await state.update_data(name=raw)
    await state.set_state(RegistrationStates.waiting_surname)
    await message.answer(
        "Шаг 1 из 3 — теперь введите вашу <b>фамилию</b> (только буквы, от 2 до 30 символов).",
        parse_mode="HTML",
    )


# ── Шаг 2: фамилия ───────────────────────────────────────────────────────────

@registration_router.message(RegistrationStates.waiting_surname)
async def process_surname(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()

    if not _validate_name_part(raw):
        await message.answer(_ERR_SURNAME)
        return

    await state.update_data(surname=raw)
    await state.set_state(RegistrationStates.choosing_role)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🏫 Классный руководитель", callback_data="reg:role:class_teacher")],
        [InlineKeyboardButton(text="🧑‍🏫 Учитель-предметник",   callback_data="reg:role:subject_teacher")],
        [InlineKeyboardButton(text="🗂 Секретарь",               callback_data="reg:role:secretary")],
        [InlineKeyboardButton(text="❌ Отменить регистрацию",    callback_data="reg:cancel")],
    ])
    await message.answer("Шаг 2 из 3 — выберите вашу роль:", reply_markup=kb)


# ── Отмена через inline-кнопку ────────────────────────────────────────────────

@registration_router.callback_query(F.data == "reg:cancel")
async def cancel_inline(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Регистрация отменена.")
    await callback.message.answer(
        "Если захотите попробовать снова — нажмите кнопку ниже.",
        reply_markup=access_request_kb,
    )
    await callback.answer()


# ── Шаг 3а: выбор роли ───────────────────────────────────────────────────────

@registration_router.callback_query(RegistrationStates.choosing_role, F.data.startswith("reg:role:"))
async def role_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    role = callback.data.split(":")[-1]
    if role not in (Role.CLASS_TEACHER, Role.SUBJECT_TEACHER, Role.SECRETARY):
        # Защита от неожиданных значений
        await callback.answer("Неверный выбор, попробуйте ещё раз.", show_alert=True)
        return

    await state.update_data(role=role)
    await callback.answer()

    schools = get_all_schools()
    if len(schools) > 1:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=s["name"], callback_data=f"reg:school:{s['id']}")]
            for s in schools
        ] + [[InlineKeyboardButton(text="❌ Отменить регистрацию", callback_data="reg:cancel")]])
        await state.set_state(RegistrationStates.choosing_school)
        await callback.message.edit_text("Шаг 3 из 3 — выберите вашу школу:", reply_markup=kb)
    else:
        school_id = schools[0]["id"] if schools else 1
        await state.update_data(school_id=school_id)
        await _proceed_after_school(callback, state, role)


# ── Шаг 3б: выбор школы (если их несколько) ──────────────────────────────────

@registration_router.callback_query(RegistrationStates.choosing_school, F.data.startswith("reg:school:"))
async def school_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    school_id = int(callback.data.split(":")[-1])
    await state.update_data(school_id=school_id)
    data = await state.get_data()
    role = data.get("role", Role.SUBJECT_TEACHER)
    await callback.answer()
    await _proceed_after_school(callback, state, role)


# ── Шаг 3в: выбор класса (только для классного руководителя) ─────────────────

async def _proceed_after_school(
    callback: CallbackQuery, state: FSMContext, role: str
) -> None:
    if role == Role.CLASS_TEACHER:
        classes = get_all_classes()
        if not classes:
            await callback.message.edit_text(
                "В системе пока нет ни одного класса. "
                "Обратитесь к администратору — он добавит классы, после чего вы сможете подать заявку."
            )
            await state.clear()
            return

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=c.name, callback_data=f"reg:class:{c.id}")]
            for c in classes
        ] + [[InlineKeyboardButton(text="❌ Отменить регистрацию", callback_data="reg:cancel")]])
        await state.set_state(RegistrationStates.choosing_class)
        await callback.message.edit_text(
            "Шаг 3 из 3 — выберите ваш класс:",
            reply_markup=kb,
        )
    else:
        # Для учителя-предметника и секретаря класс не нужен
        data = await state.get_data()
        school_id = data.get("school_id", 1)
        saved = await _save_and_notify(
            callback.from_user.id, state, callback.bot, class_id=None, school_id=school_id
        )
        if saved:
            await callback.message.edit_text(
                "✅ Заявка отправлена администратору. Как только он её рассмотрит, "
                "вы получите уведомление и сможете начать работу.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")]
                ]),
            )
        else:
            await callback.message.edit_text(
                "Вы уже подали заявку и она ожидает рассмотрения. "
                "Как только администратор примет решение, вы получите доступ.",
            )
        await state.clear()


@registration_router.callback_query(RegistrationStates.choosing_class, F.data.startswith("reg:class:"))
async def class_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    class_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    school_id = data.get("school_id", 1)

    await callback.answer()
    saved = await _save_and_notify(
        callback.from_user.id, state, callback.bot, class_id=class_id, school_id=school_id
    )
    if saved:
        await callback.message.edit_text(
            "✅ Заявка отправлена администратору. Как только он её рассмотрит, "
            "вы получите уведомление и сможете начать работу.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")]
            ]),
        )
    else:
        await callback.message.edit_text(
            "Вы уже подали заявку и она ожидает рассмотрения. "
            "Как только администратор примет решение, вы получите доступ.",
        )
    await state.clear()


# ── Сохранение заявки и уведомление администратора ───────────────────────────

async def _save_and_notify(
    user_id: int,
    state: FSMContext,
    bot: Bot,
    class_id: int | None,
    school_id: int,
) -> bool:
    """
    Сохраняет заявку в базу и уведомляет администратора.
    Возвращает True при успехе, False если pending-заявка уже существует.
    """
    # Финальная проверка на дубль прямо перед сохранением (защита от гонки)
    if has_pending_request(user_id, school_id):
        return False

    data = await state.get_data()
    name = f"{data.get('name', '')} {data.get('surname', '')}".strip()
    role = data.get("role", Role.SUBJECT_TEACHER)

    # Получаем имя класса для хранения в заявке
    class_name: str | None = None
    if class_id is not None:
        from database import Class as ClassModel
        db = SessionLocal()
        try:
            c = db.query(ClassModel).filter(ClassModel.id == class_id).first()
            class_name = c.name if c else None
        finally:
            db.close()

    schools = get_all_schools()
    school_name = next((s["name"] for s in schools if s["id"] == school_id), "Неизвестная школа")

    db = SessionLocal()
    try:
        req = RegistrationRequest(
            telegram_id=user_id,
            name=name,
            role=role,
            class_name=class_name,
            status="pending",
            school_id=school_id,
        )
        db.add(req)
        db.commit()
    finally:
        db.close()

    await bot.send_message(
        ADMIN_TELEGRAM_ID,
        f"📩 Новая заявка на доступ!\n"
        f"Имя: {name}\n"
        f"Telegram ID: {user_id}\n"
        f"Роль: {ROLE_LABELS.get(role, role)}\n"
        f"Класс: {class_name or 'не выбран'}\n"
        f"🏫 Школа: {school_name}\n\n"
        f"Одобрите или отклоните в меню администратора.",
    )
    return True