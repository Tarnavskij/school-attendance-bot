import pytest
from unittest.mock import AsyncMock, Mock, patch, ANY
from aiogram.types import Message, CallbackQuery, User, Chat, InlineKeyboardMarkup
from datetime import date
from types import SimpleNamespace

from handlers.director import director_router, school_summary, director_classes, _show_class_list, _build_class_grid_keyboard, view_class_absences, back_to_class_list, _show_absent_readonly
from core.keyboards import BTN_SCHOOL_SUMMARY, BTN_DIRECTOR_CLASSES, start_kb, back_to_menu_btn
from core.roles import Role


# ----- Фикстуры -----

@pytest.fixture
def mock_message():
    msg = AsyncMock(spec=Message)
    msg.from_user = Mock(spec=User)
    msg.from_user.id = 12345
    msg.text = BTN_SCHOOL_SUMMARY
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
    cb.data = "dir:view:1"
    return cb


@pytest.fixture
def mock_class():
    cls = SimpleNamespace(id=1, name="5А", grade=5, letter="А")
    return cls


# ----- Тесты для school_summary -----

@pytest.mark.asyncio
async def test_school_summary_no_access(mock_message):
    """Нет доступа."""
    with patch('handlers.director.check_access', return_value=False):
        await school_summary(mock_message)
        mock_message.answer.assert_called_once_with("Нет доступа.")


@pytest.mark.asyncio
async def test_school_summary_success(mock_message):
    """Успешный показ сводки."""
    mock_summary = "Сводка за сегодня"
    with patch('handlers.director.check_access', return_value=True), \
         patch('handlers.director.ReportService.get_daily_summary', return_value=mock_summary), \
         patch('handlers.director.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await school_summary(mock_message)
        mock_message.answer.assert_called_once_with(mock_summary, reply_markup=start_kb)


# ----- Тесты для director_classes -----

@pytest.mark.asyncio
async def test_director_classes_no_access(mock_message):
    """Нет доступа."""
    with patch('handlers.director.check_access', return_value=False):
        await director_classes(mock_message)
        mock_message.answer.assert_called_once_with("Нет доступа.")


@pytest.mark.asyncio
async def test_director_classes_success(mock_message):
    """Успешный показ списка классов."""
    with patch('handlers.director.check_access', return_value=True), \
         patch('handlers.director._show_class_list', new_callable=AsyncMock) as mock_show:
        await director_classes(mock_message)
        # _show_class_list вызывается с одним аргументом (edit не передаётся, используется значение по умолчанию False)
        mock_show.assert_awaited_once_with(mock_message)
# ----- Тесты для _show_class_list -----

@pytest.mark.asyncio
async def test_show_class_list_no_classes(mock_message):
    """Нет классов в базе."""
    with patch('handlers.director.get_all_classes', return_value=[]):
        await _show_class_list(mock_message, edit=False)
        mock_message.answer.assert_called_once()
        text = mock_message.answer.call_args[0][0]
        assert "Нет классов в базе." in text
        kb = mock_message.answer.call_args[1]["reply_markup"]
        assert isinstance(kb, InlineKeyboardMarkup)


@pytest.mark.asyncio
async def test_show_class_list_with_classes(mock_message):
    """Есть классы — показываем список."""
    classes = [
        SimpleNamespace(id=1, name="5А", grade=5),
        SimpleNamespace(id=2, name="5Б", grade=5),
        SimpleNamespace(id=3, name="6А", grade=6),
    ]
    with patch('handlers.director.get_all_classes', return_value=classes):
        await _show_class_list(mock_message, edit=False)
        mock_message.answer.assert_called_once()
        text = mock_message.answer.call_args[0][0]
        assert "Выберите класс" in text
        kb = mock_message.answer.call_args[1]["reply_markup"]
        assert isinstance(kb, InlineKeyboardMarkup)
        # Проверяем наличие кнопок
        buttons_texts = []
        for row in kb.inline_keyboard:
            for btn in row:
                buttons_texts.append(btn.text)
        assert "5А" in buttons_texts
        assert "5Б" in buttons_texts
        assert "6А" in buttons_texts
        assert "🔙 Назад в меню" in buttons_texts


@pytest.mark.asyncio
async def test_show_class_list_edit(mock_message):
    """Режим редактирования."""
    classes = [SimpleNamespace(id=1, name="5А", grade=5)]
    with patch('handlers.director.get_all_classes', return_value=classes):
        await _show_class_list(mock_message, edit=True)
        mock_message.edit_text.assert_called_once()
        assert "Выберите класс" in mock_message.edit_text.call_args[0][0]


# ----- Тесты для _build_class_grid_keyboard -----

def test_build_class_grid_keyboard():
    """Группировка классов по параллелям."""
    classes = [
        SimpleNamespace(id=1, name="5А", grade=5),
        SimpleNamespace(id=2, name="5Б", grade=5),
        SimpleNamespace(id=3, name="6А", grade=6),
    ]
    kb = _build_class_grid_keyboard(classes, "dir:view")
    assert isinstance(kb, InlineKeyboardMarkup)
    buttons = kb.inline_keyboard
    # Проверяем группировку: должны быть строки для 5-х и 6-х классов
    # Ищем кнопку "5А" с callback "dir:view:1"
    found = False
    for row in buttons:
        for btn in row:
            if btn.text == "5А":
                found = True
                assert btn.callback_data == "dir:view:1"
    assert found
    # Есть кнопка "Назад"
    back_found = any(btn.text == "🔙 Назад в меню" for row in buttons for btn in row)
    assert back_found


# ----- Тесты для view_class_absences -----

@pytest.mark.asyncio
async def test_view_class_absences_no_access(mock_callback):
    """Нет доступа."""
    with patch('handlers.director.check_access', return_value=False):
        await view_class_absences(mock_callback)
        mock_callback.answer.assert_called_once_with("Нет доступа.", show_alert=True)


@pytest.mark.asyncio
async def test_view_class_absences_success(mock_callback):
    """Успешный просмотр отсутствующих."""
    mock_callback.data = "dir:view:1"
    with patch('handlers.director.check_access', return_value=True), \
         patch('handlers.director._show_absent_readonly', new_callable=AsyncMock) as mock_show:
        await view_class_absences(mock_callback)
        mock_show.assert_awaited_once_with(mock_callback.message, 1)
        mock_callback.answer.assert_awaited_once()


# ----- Тесты для back_to_class_list -----

@pytest.mark.asyncio
async def test_back_to_class_list_no_access(mock_callback):
    """Нет доступа."""
    with patch('handlers.director.check_access', return_value=False):
        await back_to_class_list(mock_callback)
        mock_callback.answer.assert_called_once_with("Нет доступа.", show_alert=True)


@pytest.mark.asyncio
async def test_back_to_class_list_success(mock_callback):
    """Успешный возврат к списку классов."""
    with patch('handlers.director.check_access', return_value=True), \
         patch('handlers.director._show_class_list', new_callable=AsyncMock) as mock_show:
        await back_to_class_list(mock_callback)
        mock_show.assert_awaited_once_with(mock_callback.message, edit=True)
        mock_callback.answer.assert_awaited_once()


# ----- Тесты для _show_absent_readonly -----

@pytest.mark.asyncio
async def test_show_absent_readonly_no_absent(mock_message):
    """Нет отсутствующих."""
    with patch('handlers.director.get_absent_students_today', return_value={}), \
         patch('handlers.director.get_all_classes', return_value=[SimpleNamespace(id=1, name="5А")]), \
         patch('handlers.director.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await _show_absent_readonly(mock_message, 1)
        mock_message.edit_text.assert_called_once()
        text = mock_message.edit_text.call_args[0][0]
        assert "В классе 5А сегодня отсутствующих нет." in text
        kb = mock_message.edit_text.call_args[1]["reply_markup"]
        assert isinstance(kb, InlineKeyboardMarkup)
        # Проверяем наличие кнопок
        buttons_texts = []
        for row in kb.inline_keyboard:
            for btn in row:
                buttons_texts.append(btn.text)
        assert "↩️ К классам" in buttons_texts
        assert "🔙 Назад в меню" in buttons_texts


@pytest.mark.asyncio
async def test_show_absent_readonly_with_absent(mock_message):
    """Есть отсутствующие."""
    absent = {
        1: {"name": "Иванов И.И.", "reason": "Болеет"},
        2: {"name": "Петров П.П.", "reason": None},
    }
    with patch('handlers.director.get_absent_students_today', return_value=absent), \
         patch('handlers.director.get_all_classes', return_value=[SimpleNamespace(id=1, name="5А")]), \
         patch('handlers.director.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await _show_absent_readonly(mock_message, 1)
        mock_message.edit_text.assert_called_once()
        text = mock_message.edit_text.call_args[0][0]
        assert "Отсутствующие в классе 5А" in text
        assert "• Иванов И.И. — Болеет" in text
        assert "• Петров П.П. — причина не указана" in text
        kb = mock_message.edit_text.call_args[1]["reply_markup"]
        assert isinstance(kb, InlineKeyboardMarkup)
        buttons_texts = []
        for row in kb.inline_keyboard:
            for btn in row:
                buttons_texts.append(btn.text)
        assert "↩️ К классам" in buttons_texts
        assert "🔙 Назад в меню" in buttons_texts