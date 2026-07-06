import pytest
from unittest.mock import AsyncMock, Mock, patch
from aiogram.types import Message, CallbackQuery, User, Chat
from handlers.common import common_router, show_menu_for_user
from core.keyboards import BTN_MENU
from core.roles import Role


# ----- Фикстуры для моков -----

@pytest.fixture
def mock_message():
    msg = AsyncMock(spec=Message)
    msg.from_user = Mock(spec=User)
    msg.from_user.id = 12345
    msg.text = "some text"
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    msg.delete = AsyncMock()
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
    cb.data = "nav:menu"
    return cb


# ----- Тесты для show_menu_for_user -----

@pytest.mark.asyncio
async def test_show_menu_for_user_admin(mock_message):
    """Администратор получает меню с кнопками."""
    with patch('handlers.common.is_admin', return_value=True), \
         patch('handlers.common.build_menu_keyboard', return_value=Mock()) as mock_build:
        await show_menu_for_user(mock_message, 12345, edit=False)
        mock_message.answer.assert_called_once_with("Выберите действие:", reply_markup=mock_build.return_value)
        mock_build.assert_called_once_with(12345)


@pytest.mark.asyncio
async def test_show_menu_for_user_admin_edit(mock_message):
    """Администратор, редактируем существующее сообщение."""
    with patch('handlers.common.is_admin', return_value=True), \
         patch('handlers.common.build_menu_keyboard', return_value=Mock()) as mock_build:
        await show_menu_for_user(mock_message, 12345, edit=True)
        mock_message.edit_text.assert_called_once_with("Выберите действие:", reply_markup=mock_build.return_value)
        mock_build.assert_called_once_with(12345)
        mock_message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_show_menu_for_user_registered_teacher(mock_message):
    """Зарегистрированный не-админ получает меню по роли."""
    mock_teacher = Mock()
    mock_teacher.role = Role.SUBJECT_TEACHER
    with patch('handlers.common.is_admin', return_value=False), \
         patch('handlers.common.get_teacher_by_telegram_id', return_value=mock_teacher), \
         patch('handlers.common.build_menu_keyboard', return_value=Mock()) as mock_build:
        await show_menu_for_user(mock_message, 12345, edit=False)
        mock_message.answer.assert_called_once_with("Выберите действие:", reply_markup=mock_build.return_value)
        mock_build.assert_called_once_with(12345)


@pytest.mark.asyncio
async def test_show_menu_for_user_unregistered(mock_message):
    """Незарегистрированный пользователь получает кнопку 'Запросить доступ'."""
    mock_kb = Mock()
    with patch('handlers.common.is_admin', return_value=False), \
         patch('handlers.common.get_teacher_by_telegram_id', return_value=None), \
         patch('handlers.common.access_request_kb', mock_kb):
        await show_menu_for_user(mock_message, 12345, edit=False)
        mock_message.answer.assert_called_once_with(
            "Вы не зарегистрированы. Нажмите кнопку, чтобы запросить доступ.",
            reply_markup=mock_kb
        )


@pytest.mark.asyncio
async def test_show_menu_for_user_unregistered_edit(mock_message):
    """Незарегистрированный, редактирование — отправляем новое сообщение."""
    mock_kb = Mock()
    with patch('handlers.common.is_admin', return_value=False), \
         patch('handlers.common.get_teacher_by_telegram_id', return_value=None), \
         patch('handlers.common.access_request_kb', mock_kb):
        await show_menu_for_user(mock_message, 12345, edit=True)
        mock_message.answer.assert_called_once_with(
            "Вы не зарегистрированы. Нажмите кнопку, чтобы запросить доступ.",
            reply_markup=mock_kb
        )
        mock_message.edit_text.assert_not_called()


# ----- Тесты для хендлеров -----

@pytest.mark.asyncio
async def test_cmd_start(mock_message):
    """Команда /start вызывает show_menu_for_user."""
    with patch('handlers.common.show_menu_for_user', new_callable=AsyncMock) as mock_show:
        from handlers.common import cmd_start
        await cmd_start(mock_message)
        mock_show.assert_awaited_once_with(mock_message, 12345)


@pytest.mark.asyncio
async def test_show_menu_by_button(mock_message):
    """Нажатие кнопки «Меню» вызывает show_menu_for_user."""
    mock_message.text = BTN_MENU
    with patch('handlers.common.show_menu_for_user', new_callable=AsyncMock) as mock_show:
        from handlers.common import show_menu
        await show_menu(mock_message)
        mock_show.assert_awaited_once_with(mock_message, 12345)


@pytest.mark.asyncio
async def test_show_menu_by_command(mock_message):
    """Команда /menu вызывает show_menu_for_user."""
    mock_message.text = "/menu"
    with patch('handlers.common.show_menu_for_user', new_callable=AsyncMock) as mock_show:
        from handlers.common import show_menu
        await show_menu(mock_message)
        mock_show.assert_awaited_once_with(mock_message, 12345)


@pytest.mark.asyncio
async def test_nav_to_menu(mock_callback):
    """Обработчик nav:menu удаляет сообщение и вызывает show_menu_for_user."""
    with patch('handlers.common.show_menu_for_user', new_callable=AsyncMock) as mock_show:
        from handlers.common import nav_to_menu
        await nav_to_menu(mock_callback)
        mock_callback.message.delete.assert_awaited_once()
        mock_show.assert_awaited_once_with(mock_callback.message, mock_callback.from_user.id)
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_fallback_any_message(mock_message):
    """Любое другое сообщение вызывает show_menu_for_user."""
    with patch('handlers.common.show_menu_for_user', new_callable=AsyncMock) as mock_show:
        from handlers.common import fallback_any_message
        await fallback_any_message(mock_message)
        mock_show.assert_awaited_once_with(mock_message, 12345)