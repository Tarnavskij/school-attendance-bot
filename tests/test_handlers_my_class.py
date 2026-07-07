import pytest
from unittest.mock import AsyncMock, Mock, patch, ANY
from aiogram.types import Message, CallbackQuery, User, Chat, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from datetime import date
from types import SimpleNamespace

from handlers.my_class import my_class_router, my_class_handler, view_class, show_reason_menu, apply_reason, _get_school_id, _build_class_grid_keyboard, _show_absent_list
from core.keyboards import BTN_MY_CLASS, back_to_menu_btn
from core.roles import Role
from core.constants import ABSENCE_REASONS


# ----- Фикстуры -----

@pytest.fixture
def mock_message():
    msg = AsyncMock(spec=Message)
    msg.from_user = Mock(spec=User)
    msg.from_user.id = 12345
    msg.text = BTN_MY_CLASS
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    msg.delete = AsyncMock()
    msg.chat = Mock(spec=Chat)
    msg.chat.id = 67890
    return msg


@pytest.fixture
def mock_callback():
    cb = AsyncMock(spec=CallbackQuery)
    cb.from_user = Mock(spec=User)
    cb.from_user.id = 12345
    cb.message = AsyncMock(spec=Message)
    cb.message.delete = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    cb.data = "mc:view:1"
    cb.bot = AsyncMock()
    return cb


@pytest.fixture
def mock_teacher():
    teacher = Mock()
    teacher.id = 1
    teacher.school_id = 1
    teacher.class_id = 5
    return teacher


@pytest.fixture
def mock_class():
    cls = SimpleNamespace(id=1, name="5А", school_id=1, grade=5)
    return cls


# ----- Тесты для my_class_handler -----

@pytest.mark.asyncio
async def test_my_class_handler_no_access(mock_message):
    """Нет прав доступа."""
    with patch('handlers.my_class.check_access', return_value=False):
        await my_class_handler(mock_message)
        mock_message.answer.assert_called_once_with("У вас нет закреплённого класса.")


@pytest.mark.asyncio
async def test_my_class_handler_admin_no_classes(mock_message):
    """Администратор, но нет классов."""
    with patch('handlers.my_class.check_access', return_value=True), \
         patch('handlers.my_class.is_admin', return_value=True), \
         patch('handlers.my_class.get_all_classes', return_value=[]):
        await my_class_handler(mock_message)
        mock_message.answer.assert_called_once_with("Нет доступных классов.")


@pytest.mark.asyncio
async def test_my_class_handler_admin_with_classes(mock_message):
    """Администратор, есть классы — показывает список."""
    classes = [SimpleNamespace(id=1, name="5А", grade=5, letter="А")]
    with patch('handlers.my_class.check_access', return_value=True), \
         patch('handlers.my_class.is_admin', return_value=True), \
         patch('handlers.my_class.get_all_classes', return_value=classes), \
         patch('handlers.my_class._build_class_grid_keyboard', return_value=Mock()) as mock_kb:
        await my_class_handler(mock_message)
        # Используем ANY для reply_markup, так как это не тот же объект
        mock_message.answer.assert_called_once_with("Выберите класс для просмотра:", reply_markup=ANY)


@pytest.mark.asyncio
async def test_my_class_handler_class_teacher_no_class(mock_message):
    """Классный руководитель без привязанного класса."""
    with patch('handlers.my_class.check_access', return_value=True), \
         patch('handlers.my_class.is_admin', return_value=False), \
         patch('handlers.my_class.get_teacher_by_telegram_id', return_value=Mock(class_id=None)):
        await my_class_handler(mock_message)
        mock_message.answer.assert_called_once_with("У вас не указан класс. Обратитесь к администратору.")


@pytest.mark.asyncio
async def test_my_class_handler_class_teacher_with_class(mock_message):
    """Классный руководитель с привязанным классом — показывает список отсутствующих."""
    teacher = Mock()
    teacher.class_id = 5
    teacher.school_id = 1
    with patch('handlers.my_class.check_access', return_value=True), \
         patch('handlers.my_class.is_admin', return_value=False), \
         patch('handlers.my_class.get_teacher_by_telegram_id', return_value=teacher), \
         patch('handlers.my_class._show_absent_list', new_callable=AsyncMock) as mock_show:
        await my_class_handler(mock_message)
        mock_show.assert_awaited_once_with(mock_message, 5, 1, edit=False)


# ----- Тесты для view_class -----

@pytest.mark.asyncio
async def test_view_class_no_access(mock_callback):
    """Нет доступа."""
    with patch('handlers.my_class.check_access', return_value=False):
        await view_class(mock_callback)
        mock_callback.answer.assert_called_once_with("Нет доступа.", show_alert=True)


@pytest.mark.asyncio
async def test_view_class_success(mock_callback):
    """Успешный просмотр класса."""
    mock_callback.data = "mc:view:1"
    with patch('handlers.my_class.check_access', return_value=True), \
         patch('handlers.my_class._get_school_id', return_value=1), \
         patch('handlers.my_class._show_absent_list', new_callable=AsyncMock) as mock_show:
        await view_class(mock_callback)
        mock_show.assert_awaited_once_with(mock_callback.message, 1, 1, edit=True)
        mock_callback.answer.assert_awaited_once()


# ----- Тесты для show_reason_menu -----

@pytest.mark.asyncio
async def test_show_reason_menu_no_access(mock_callback):
    """Нет доступа."""
    mock_callback.data = "mc:reason_menu:1:1"
    with patch('handlers.my_class.check_access', return_value=False):
        await show_reason_menu(mock_callback)
        mock_callback.answer.assert_called_once_with("Нет доступа.", show_alert=True)


@pytest.mark.asyncio
async def test_show_reason_menu_success(mock_callback):
    """Успешный показ меню выбора причины."""
    mock_callback.data = "mc:reason_menu:1:5"
    absent = {1: {"name": "Иванов И.И.", "reason": None}}
    with patch('handlers.my_class.check_access', return_value=True), \
         patch('handlers.my_class._get_school_id', return_value=1), \
         patch('handlers.my_class.get_absent_students_today', return_value=absent), \
         patch('handlers.my_class.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await show_reason_menu(mock_callback)
        mock_callback.message.edit_text.assert_called_once()
        assert "Иванов И.И." in mock_callback.message.edit_text.call_args[0][0]


# ----- Тесты для apply_reason -----

@pytest.mark.asyncio
async def test_apply_reason_no_access(mock_callback):
    """Нет доступа."""
    mock_callback.data = "mc:reason:1:5:0"
    with patch('handlers.my_class.check_access', return_value=False):
        await apply_reason(mock_callback)
        mock_callback.answer.assert_called_once_with("Нет доступа.", show_alert=True)


@pytest.mark.asyncio
async def test_apply_reason_success(mock_callback):
    """Успешное применение причины."""
    mock_callback.data = "mc:reason:1:5:0"  # student_id=1, class_id=5, reason_idx=0
    with patch('handlers.my_class.check_access', return_value=True), \
         patch('handlers.my_class._get_school_id', return_value=1), \
         patch('handlers.my_class.set_absence_reason') as mock_set, \
         patch('handlers.my_class.date') as mock_date, \
         patch('handlers.my_class._show_absent_list', new_callable=AsyncMock) as mock_show:
        mock_date.today = Mock(return_value=date.today())
        await apply_reason(mock_callback)
        mock_set.assert_called_once_with(1, 5, date.today(), ABSENCE_REASONS[0], school_id=1)
        mock_callback.answer.assert_called_once_with("Причина сохранена.")
        mock_show.assert_awaited_once_with(mock_callback.message, 5, 1, edit=True)


# ----- Тесты для _get_school_id -----

def test_get_school_id_for_admin():
    """Администратор — возвращает глобальный school_id."""
    with patch('handlers.my_class.is_admin', return_value=True), \
         patch('handlers.my_class.get_current_school_id', return_value=42):
        assert _get_school_id(123) == 42


def test_get_school_id_for_teacher():
    """Учитель — возвращает school_id из профиля."""
    teacher = Mock(school_id=10)
    with patch('handlers.my_class.is_admin', return_value=False), \
         patch('handlers.my_class.get_teacher_by_telegram_id', return_value=teacher):
        assert _get_school_id(123) == 10


def test_get_school_id_fallback():
    """Если учитель не найден — возвращает глобальный."""
    with patch('handlers.my_class.is_admin', return_value=False), \
         patch('handlers.my_class.get_teacher_by_telegram_id', return_value=None), \
         patch('handlers.my_class.get_current_school_id', return_value=99):
        assert _get_school_id(123) == 99


# ----- Тесты для _build_class_grid_keyboard -----

def test_build_class_grid_keyboard():
    """Клавиатура группирует классы по параллелям."""
    classes = [
        SimpleNamespace(id=1, name="5А", grade=5),
        SimpleNamespace(id=2, name="5Б", grade=5),
        SimpleNamespace(id=3, name="6А", grade=6),
    ]
    kb = _build_class_grid_keyboard(classes, "mc:view")
    assert isinstance(kb, InlineKeyboardMarkup)
    buttons = kb.inline_keyboard
    # Проверяем, что есть кнопка "5А" с callback "mc:view:1"
    found = False
    for row in buttons:
        for btn in row:
            if btn.text == "5А":
                found = True
                assert btn.callback_data == "mc:view:1"
    assert found
    # Есть кнопка назад
    back_found = any(btn.text == "🔙 Назад в меню" for row in buttons for btn in row)
    assert back_found


# ----- Тесты для _show_absent_list -----

@pytest.mark.asyncio
async def test_show_absent_list_no_absent(mock_message):
    """Нет отсутствующих."""
    with patch('handlers.my_class.get_absent_students_today', return_value={}), \
         patch('handlers.my_class.get_all_classes', return_value=[SimpleNamespace(id=1, name="5А")]), \
         patch('handlers.my_class.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await _show_absent_list(mock_message, 1, 1, edit=False)
        mock_message.answer.assert_called_once()
        assert "отсутствующих нет" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_show_absent_list_with_absent(mock_message):
    """Есть отсутствующие — проверяем, что кнопки содержат имена с причинами."""
    absent = {
        1: {"name": "Иванов И.И.", "reason": "Болеет"},
        2: {"name": "Петров П.П.", "reason": None},
    }
    with patch('handlers.my_class.get_absent_students_today', return_value=absent), \
         patch('handlers.my_class.get_all_classes', return_value=[SimpleNamespace(id=1, name="5А")]), \
         patch('handlers.my_class.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await _show_absent_list(mock_message, 1, 1, edit=False)
        mock_message.answer.assert_called_once()
        # Проверяем текст сообщения
        text = mock_message.answer.call_args[0][0]
        assert "Отсутствующие в классе 5А" in text
        # Проверяем, что клавиатура содержит кнопки с нужными текстами
        kb = mock_message.answer.call_args[1]["reply_markup"]
        assert isinstance(kb, InlineKeyboardMarkup)
        buttons_texts = []
        for row in kb.inline_keyboard:
            for btn in row:
                buttons_texts.append(btn.text)
        # Ищем кнопку с "Иванов И.И. (Болеет)" и "Петров П.П."
        assert "Иванов И.И. (Болеет)" in buttons_texts
        assert "Петров П.П." in buttons_texts
        # Проверяем callback для первого студента
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.text == "Иванов И.И. (Болеет)":
                    assert btn.callback_data == "mc:reason_menu:1:1"


@pytest.mark.asyncio
async def test_show_absent_list_edit(mock_message):
    """Режим редактирования."""
    with patch('handlers.my_class.get_absent_students_today', return_value={}), \
         patch('handlers.my_class.get_all_classes', return_value=[SimpleNamespace(id=1, name="5А")]), \
         patch('handlers.my_class.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await _show_absent_list(mock_message, 1, 1, edit=True)
        mock_message.edit_text.assert_called_once()
        assert "отсутствующих нет" in mock_message.edit_text.call_args[0][0]