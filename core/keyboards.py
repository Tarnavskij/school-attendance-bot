# core/keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from core.roles import Role, is_admin
from repositories import get_teacher_by_telegram_id

# ── Button labels ─────────────────────────────────────────────────────────────

BTN_MENU = "📋 Меню"
BTN_START_ROLL = "🧑‍🏫 Начать перекличку"
BTN_MY_CLASS = "👨‍🏫 Мой класс"
BTN_MEAL = "🍽️ Питание"                      # для классных руководителей
BTN_ANALYTICS = "📊 Аналитика"               # для классных руководителей
BTN_CHEF_MEAL = "🍽️ Сводка питания"          # для шеф-повара
BTN_CHEF_FREE = "🆓 Бесплатники"             # для шеф-повара
BTN_SCHOOL_SUMMARY = "📊 Сводка по школе"
BTN_EXPORT_ABSENCES = "📥 Экспорт пропусков" # для директора и секретаря
BTN_TEACHER_LIST = "👥 Пользователи"
BTN_STUDENTS = "🎓 Ученики"
BTN_REQUEST_ACCESS = "🚪 Получить доступ"
BTN_DIRECTOR_CLASSES = "🏫 Классы"
BTN_ROLL_STATUS = "📋 Статус переклички"
BTN_SCHOOLS = "🏫 Школы"
BTN_ADMIN_MEAL = "🍽️ Управление питанием"    # для администратора
BTN_ATTENDANCE_GRAPH = "📅 График"            # для директора и админа

# Все reply-кнопки, которые пользователь может нажать в любой момент.
# Нужны, чтобы state-хендлеры (например, «напишите, а не нажимайте кнопки»)
# НЕ съедали их и пропускали дальше по цепочке роутеров.
ALL_MENU_BUTTONS = [
    BTN_MENU, BTN_START_ROLL, BTN_MY_CLASS, BTN_MEAL, BTN_ANALYTICS,
    BTN_CHEF_MEAL, BTN_CHEF_FREE, BTN_SCHOOL_SUMMARY, BTN_EXPORT_ABSENCES, BTN_TEACHER_LIST, BTN_STUDENTS,
    BTN_REQUEST_ACCESS, BTN_DIRECTOR_CLASSES, BTN_ROLL_STATUS, BTN_SCHOOLS,
    BTN_ADMIN_MEAL, BTN_ATTENDANCE_GRAPH,
]


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
            [KeyboardButton(text=BTN_STUDENTS), KeyboardButton(text=BTN_SCHOOLS)],
            [KeyboardButton(text=BTN_ADMIN_MEAL)],
            [KeyboardButton(text=BTN_ATTENDANCE_GRAPH)],  # новая кнопка для админа
        ]
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    teacher = get_teacher_by_telegram_id(user_id)
    if not teacher:
        return ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)

    role = teacher.role
    if role == Role.DIRECTOR:
        rows = [
            [KeyboardButton(text=BTN_SCHOOL_SUMMARY), KeyboardButton(text=BTN_DIRECTOR_CLASSES)],
            [KeyboardButton(text=BTN_ATTENDANCE_GRAPH), KeyboardButton(text=BTN_EXPORT_ABSENCES)],
        ]
    elif role == Role.SUBJECT_TEACHER:
        rows = [[KeyboardButton(text=BTN_START_ROLL)]]
    elif role == Role.CLASS_TEACHER:
        rows = [
            [KeyboardButton(text=BTN_START_ROLL), KeyboardButton(text=BTN_MY_CLASS)],
            [KeyboardButton(text=BTN_MEAL), KeyboardButton(text=BTN_ANALYTICS)],
        ]
    elif role == Role.SECRETARY:
        rows = [
        [KeyboardButton(text=BTN_ROLL_STATUS)]],
        [KeyboardButton(text=BTN_EXPORT_ABSENCES)],
    elif role == Role.CHEF:
        rows = [[KeyboardButton(text=BTN_CHEF_MEAL), KeyboardButton(text=BTN_CHEF_FREE)]]
    else:
        rows = []

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


# ── Inline keyboard helpers ───────────────────────────────────────────────────

def back_to_menu_btn() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")


def cancel_btn(callback_data: str = "nav:menu") -> InlineKeyboardButton:
    return InlineKeyboardButton(text="❌ Отмена", callback_data=callback_data)