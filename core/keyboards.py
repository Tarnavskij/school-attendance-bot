# core/keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from core.roles import Role, is_admin
from repositories import get_teacher_by_telegram_id

# ── Button labels ─────────────────────────────────────────────────────────────

BTN_MENU = "📋 Меню"
BTN_START_ROLL = "🧑‍🏫 Начать перекличку"
BTN_MY_CLASS = "👨‍🏫 Мой класс"
BTN_SCHOOL_SUMMARY = "📊 Сводка по школе"
BTN_TEACHER_LIST = "👥 Пользователи"
BTN_STUDENTS = "🎓 Ученики"
BTN_REQUEST_ACCESS = "🚪 Получить доступ"
BTN_DIRECTOR_CLASSES = "🏫 Классы"
BTN_ROLL_STATUS = "📋 Статус переклички"

# ── Reply keyboards ───────────────────────────────────────────────────────────

start_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_MENU)]],
    resize_keyboard=True,
)

access_request_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_REQUEST_ACCESS)]],
    resize_keyboard=True,
)


def build_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    if is_admin(user_id):
        rows = [
            [KeyboardButton(text=BTN_START_ROLL), KeyboardButton(text=BTN_MY_CLASS)],
            [KeyboardButton(text=BTN_SCHOOL_SUMMARY), KeyboardButton(text=BTN_TEACHER_LIST)],
            [KeyboardButton(text=BTN_STUDENTS)],
        ]
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    teacher = get_teacher_by_telegram_id(user_id)
    if not teacher:
        return ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)

    role = teacher.role
    if role == Role.DIRECTOR:
        rows = [[KeyboardButton(text=BTN_SCHOOL_SUMMARY), KeyboardButton(text=BTN_DIRECTOR_CLASSES)]]
    elif role == Role.SUBJECT_TEACHER:
        rows = [[KeyboardButton(text=BTN_START_ROLL)]]
    elif role == Role.CLASS_TEACHER:
        rows = [[KeyboardButton(text=BTN_START_ROLL), KeyboardButton(text=BTN_MY_CLASS)]]
    elif role == Role.SECRETARY:
        rows = [[KeyboardButton(text=BTN_ROLL_STATUS)]]
    else:
        rows = []

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


# ── Inline keyboard helpers ───────────────────────────────────────────────────

def back_to_menu_btn() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")


def cancel_btn(callback_data: str = "nav:menu") -> InlineKeyboardButton:
    return InlineKeyboardButton(text="❌ Отмена", callback_data=callback_data)