import pytest
from unittest.mock import AsyncMock, Mock, patch
from aiogram.types import Message, User
from datetime import date

from handlers.chef import chef_meal_summary
from core.keyboards import BTN_CHEF_MEAL
from core.roles import Role


# ----- Фикстуры -----

@pytest.fixture
def mock_message():
    msg = AsyncMock(spec=Message)
    msg.from_user = Mock(spec=User)
    msg.from_user.id = 12345
    msg.text = BTN_CHEF_MEAL
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
def mock_chef():
    chef = Mock()
    chef.id = 1
    chef.school_id = 1
    return chef


# ----- Тесты -----

@pytest.mark.asyncio
async def test_chef_meal_summary_no_access(mock_message):
    """Нет прав доступа (не шеф-повар) — хендлер ничего не делает."""
    with patch('handlers.chef.check_access', return_value=False):
        await chef_meal_summary(mock_message)
        mock_message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_chef_meal_summary_chef_not_found(mock_message):
    """Шеф-повар не найден в базе — хендлер ничего не делает."""
    with patch('handlers.chef.check_access', return_value=True), \
         patch('handlers.chef.get_teacher_by_telegram_id', return_value=None):
        await chef_meal_summary(mock_message)
        mock_message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_chef_meal_summary_success(mock_message, mock_chef):
    """Успешный показ сводки питания для шеф-повара."""
    mock_summary = "🍽️ Питание на 07.07.2026\n5А: всего 25 (платно 15, бесплатно 10) — Иванова"
    with patch('handlers.chef.check_access', return_value=True), \
         patch('handlers.chef.get_teacher_by_telegram_id', return_value=mock_chef), \
         patch('handlers.chef.get_meal_summary', return_value=mock_summary):
        await chef_meal_summary(mock_message)
        mock_message.answer.assert_called_once_with(mock_summary)


@pytest.mark.asyncio
async def test_chef_meal_summary_empty_summary(mock_message, mock_chef):
    """Сводка пустая — показываем сообщение 'заявок нет'."""
    mock_summary = "🍽️ На 07.07.2026 заявок нет."
    with patch('handlers.chef.check_access', return_value=True), \
         patch('handlers.chef.get_teacher_by_telegram_id', return_value=mock_chef), \
         patch('handlers.chef.get_meal_summary', return_value=mock_summary):
        await chef_meal_summary(mock_message)
        mock_message.answer.assert_called_once_with(mock_summary)
