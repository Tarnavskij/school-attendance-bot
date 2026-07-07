import pytest
from unittest.mock import AsyncMock, Mock, patch
from aiogram.types import Message, User, Chat
from datetime import date

from handlers.secretary import roll_status
from core.keyboards import BTN_ROLL_STATUS
from core.roles import Role
from core.constants import ABSENCE_REASONS


# ----- Фикстуры -----

@pytest.fixture
def mock_message():
    msg = AsyncMock(spec=Message)
    msg.from_user = Mock(spec=User)
    msg.from_user.id = 12345
    msg.text = BTN_ROLL_STATUS
    msg.answer = AsyncMock()
    return msg


# ----- Тесты -----

@pytest.mark.asyncio
async def test_roll_status_no_access(mock_message):
    """Нет доступа."""
    with patch('handlers.secretary.check_access', return_value=False):
        await roll_status(mock_message)
        mock_message.answer.assert_called_once_with("Нет доступа.")


@pytest.mark.asyncio
async def test_roll_status_in_progress(mock_message):
    """Перекличка ещё в процессе."""
    with patch('handlers.secretary.check_access', return_value=True), \
         patch('handlers.secretary.is_school_done_today', return_value=False), \
         patch('handlers.secretary.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await roll_status(mock_message)
        mock_message.answer.assert_called_once_with("⏳ Перекличка в процессе.")


@pytest.mark.asyncio
async def test_roll_status_done_no_absent(mock_message):
    """Перекличка завершена, отсутствующих нет."""
    counts = {"__total__": 0}
    with patch('handlers.secretary.check_access', return_value=True), \
         patch('handlers.secretary.is_school_done_today', return_value=True), \
         patch('handlers.secretary.get_absence_reason_counts', return_value=counts), \
         patch('handlers.secretary.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await roll_status(mock_message)
        text = mock_message.answer.call_args[0][0]
        assert "✅ Перекличка готова." in text
        assert "Всего отсутствует: 0" in text
        for reason in ABSENCE_REASONS:
            assert f"{reason}: 0" in text


@pytest.mark.asyncio
async def test_roll_status_done_with_absent(mock_message):
    """Перекличка завершена, есть отсутствующие по разным причинам."""
    counts = {
        "__total__": 5,
        "🤒 По болезни": 2,
        "📄 По заявлению": 1,
        "🏖 На оздоровлении": 1,
        "❓ Без уважительной причины": 1,
    }
    with patch('handlers.secretary.check_access', return_value=True), \
         patch('handlers.secretary.is_school_done_today', return_value=True), \
         patch('handlers.secretary.get_absence_reason_counts', return_value=counts), \
         patch('handlers.secretary.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await roll_status(mock_message)
        text = mock_message.answer.call_args[0][0]
        assert "✅ Перекличка готова." in text
        assert "Всего отсутствует: 5" in text
        for reason in ABSENCE_REASONS:
            expected_count = counts.get(reason, 0)
            assert f"{reason}: {expected_count}" in text