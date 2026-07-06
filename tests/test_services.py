import pytest
from datetime import date, datetime
from unittest.mock import Mock, patch, AsyncMock
from services import AttendanceService, ReportService
from repositories import SessionAlreadyExists
from config import ADMIN_TELEGRAM_ID

# ----- Тесты для AttendanceService -----

def test_start_attendance_success():
    """Успешный старт переклички."""
    mock_teacher = Mock()
    mock_teacher.id = 1
    mock_teacher.school_id = 1
    mock_students = [Mock(id=1), Mock(id=2)]

    with patch('services.get_teacher_by_telegram_id', return_value=mock_teacher), \
         patch('services.get_available_classes', return_value=[Mock(id=1)]), \
         patch('services.create_session', return_value=Mock(id=10)), \
         patch('services.get_students_by_class', return_value=mock_students), \
         patch('services.add_records') as mock_add:

        session, result = AttendanceService.start_attendance(123, 1, teacher_school_id=1)
        assert session is not None
        assert session.id == 10
        mock_add.assert_called_once_with(10, [1, 2])

def test_start_attendance_not_registered():
    """Пользователь не зарегистрирован."""
    with patch('services.get_teacher_by_telegram_id', return_value=None):
        session, result = AttendanceService.start_attendance(123, 1)
        assert session is None
        assert "не зарегистрированы" in result

def test_start_attendance_class_unavailable():
    """Класс уже занят или недоступен."""
    mock_teacher = Mock()
    mock_teacher.id = 1
    with patch('services.get_teacher_by_telegram_id', return_value=mock_teacher), \
         patch('services.get_available_classes', return_value=[]):
        session, result = AttendanceService.start_attendance(123, 1)
        assert session is None
        assert "уже занят" in result

def test_start_attendance_session_exists():
    """Класс уже отмечался сегодня (SessionAlreadyExists)."""
    mock_teacher = Mock()
    mock_teacher.id = 1
    with patch('services.get_teacher_by_telegram_id', return_value=mock_teacher), \
         patch('services.get_available_classes', return_value=[Mock(id=1)]), \
         patch('services.create_session', side_effect=SessionAlreadyExists("already")):
        session, result = AttendanceService.start_attendance(123, 1)
        assert session is None
        assert "уже занят" in result

def test_toggle_student():
    """Переключение статуса ученика."""
    with patch('services.toggle_student_presence', return_value=False) as mock_toggle:
        result = AttendanceService.toggle_student(10, 5)
        assert result is False
        mock_toggle.assert_called_once_with(10, 5)

def test_complete_session():
    """Завершение сессии."""
    with patch('services.finish_session') as mock_finish:
        AttendanceService.complete_session(10)
        mock_finish.assert_called_once_with(10, auto=False)

# ----- Тесты для ReportService -----

@pytest.mark.asyncio
async def test_finalize_day():
    """Завершение дня: закрыть активные сессии и отправить отчёт."""
    mock_bot = AsyncMock()
    mock_active = [Mock(id=1), Mock(id=2)]
    with patch('services.get_active_sessions', return_value=mock_active), \
         patch('services.finish_session') as mock_finish, \
         patch('services.ReportService.send_report', new_callable=AsyncMock) as mock_send:
        await ReportService.finalize_day(mock_bot)
        assert mock_finish.call_count == 2
        mock_finish.assert_any_call(1, auto=True)
        mock_finish.assert_any_call(2, auto=True)
        mock_send.assert_awaited_once_with(mock_bot)

@pytest.mark.asyncio
async def test_send_report():
    """Отправка отчёта администратору."""
    mock_bot = AsyncMock()
    mock_summary = "Сводка за сегодня"
    with patch('services.ReportService.get_daily_summary', return_value=mock_summary):
        await ReportService.send_report(mock_bot)
        mock_bot.send_message.assert_called_once_with(ADMIN_TELEGRAM_ID, mock_summary)

def test_get_daily_summary_no_sessions():
    """Нет сессий — возвращает сообщение об этом."""
    with patch('services.get_sessions_for_report', return_value=[]):
        result = ReportService.get_daily_summary(date.today())
        assert "перекличек не проводилось" in result

def test_get_daily_summary_with_sessions():
    """Сводка с несколькими сессиями."""
    mock_session_1 = Mock()
    mock_session_1.class_name = "5A"
    mock_session_1.teacher_name = "Иванов"
    mock_session_1.absent = [("Петров", None)]

    mock_session_2 = Mock()
    mock_session_2.class_name = "5B"
    mock_session_2.teacher_name = "Петрова"
    mock_session_2.absent = []

    with patch('services.get_sessions_for_report', return_value=[mock_session_1, mock_session_2]):
        result = ReportService.get_daily_summary(date.today())
        assert "5A" in result
        assert "отмечал Иванов" in result
        assert "• Петров" in result
        assert "5B" in result
        assert "отсутствующих нет" in result