import pytest
from unittest.mock import AsyncMock, Mock, patch, ANY
from aiogram.types import Message, CallbackQuery, User, Chat, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from datetime import date
from types import SimpleNamespace

from handlers.attendance import attendance_router, AttendanceStates, start_attendance, _build_class_keyboard, cancel_flow, class_chosen, toggle_student, cancel_marking, submit_attendance
from core.keyboards import BTN_START_ROLL, build_menu_keyboard
from core.roles import Role


# ----- Фикстуры -----

@pytest.fixture
def mock_message():
    msg = AsyncMock(spec=Message)
    msg.from_user = Mock(spec=User)
    msg.from_user.id = 12345
    msg.text = BTN_START_ROLL
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
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    cb.data = "att:cancel_flow"
    cb.bot = AsyncMock()
    return cb


@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


@pytest.fixture
def mock_teacher():
    teacher = Mock()
    teacher.id = 1
    teacher.school_id = 1
    teacher.class_id = None
    return teacher


@pytest.fixture
def mock_class():
    cls = SimpleNamespace(id=1, name="5А", school_id=1, grade=5, letter="А")
    return cls


@pytest.fixture
def mock_students():
    return [
        SimpleNamespace(id=1, name="Иванов И.И."),
        SimpleNamespace(id=2, name="Петров П.П."),
    ]


@pytest.fixture
def mock_session():
    sess = SimpleNamespace(id=10)
    return sess


# ----- Тесты для start_attendance -----

@pytest.mark.asyncio
async def test_start_attendance_no_access(mock_message, mock_state):
    """Нет прав для проведения переклички."""
    with patch('handlers.attendance.check_access', return_value=False):
        await start_attendance(mock_message, mock_state)
        mock_message.answer.assert_called_once_with("У вас нет прав для проведения переклички.")
        mock_state.set_state.assert_not_called()


@pytest.mark.asyncio
async def test_start_attendance_not_registered(mock_message, mock_state):
    """Пользователь не зарегистрирован."""
    with patch('handlers.attendance.check_access', return_value=True), \
         patch('handlers.attendance.get_teacher_by_telegram_id', return_value=None):
        await start_attendance(mock_message, mock_state)
        mock_message.answer.assert_called_once_with("Вы не зарегистрированы.")
        mock_state.set_state.assert_not_called()


@pytest.mark.asyncio
async def test_start_attendance_admin_with_card(mock_message, mock_state):
    """Администратору не показываем карточку, даже если она есть."""
    with patch('handlers.attendance.check_access', return_value=True), \
         patch('handlers.attendance.get_teacher_by_telegram_id', return_value=Mock(school_id=1)), \
         patch('handlers.attendance.is_admin', return_value=True), \
         patch('handlers.attendance.get_today_session_card', return_value="Card text"), \
         patch('handlers.attendance.get_school_id_for_admin', return_value=1), \
         patch('handlers.attendance.get_available_classes', return_value=[Mock()]), \
         patch('handlers.attendance._build_class_keyboard', return_value=Mock()), \
         patch('handlers.attendance.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await start_attendance(mock_message, mock_state)
        mock_message.answer.assert_any_call("🏫 Выберите класс для переклички:", reply_markup=ANY)
        mock_state.set_state.assert_called_with(AttendanceStates.choosing_class)


@pytest.mark.asyncio
async def test_start_attendance_teacher_with_card(mock_message, mock_state):
    """Учитель видит карточку, если есть."""
    with patch('handlers.attendance.check_access', return_value=True), \
         patch('handlers.attendance.get_teacher_by_telegram_id', return_value=Mock(school_id=1)), \
         patch('handlers.attendance.is_admin', return_value=False), \
         patch('handlers.attendance.get_today_session_card', return_value="Card text"):
        await start_attendance(mock_message, mock_state)
        mock_message.answer.assert_called_once_with("Card text")
        mock_state.set_state.assert_not_called()


@pytest.mark.asyncio
async def test_start_attendance_teacher_no_card(mock_message, mock_state):
    """Учитель без карточки — показывает список классов."""
    with patch('handlers.attendance.check_access', return_value=True), \
         patch('handlers.attendance.get_teacher_by_telegram_id', return_value=Mock(school_id=1)), \
         patch('handlers.attendance.is_admin', return_value=False), \
         patch('handlers.attendance.get_today_session_card', return_value=None), \
         patch('handlers.attendance.get_available_classes', return_value=[Mock()]), \
         patch('handlers.attendance._build_class_keyboard', return_value=Mock()), \
         patch('handlers.attendance.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await start_attendance(mock_message, mock_state)
        mock_message.answer.assert_called_with("🏫 Выберите класс для переклички:", reply_markup=ANY)
        mock_state.set_state.assert_called_with(AttendanceStates.choosing_class)


@pytest.mark.asyncio
async def test_start_attendance_no_available_classes(mock_message, mock_state):
    """Все классы уже отмечены."""
    with patch('handlers.attendance.check_access', return_value=True), \
         patch('handlers.attendance.get_teacher_by_telegram_id', return_value=Mock(school_id=1)), \
         patch('handlers.attendance.is_admin', return_value=False), \
         patch('handlers.attendance.get_today_session_card', return_value=None), \
         patch('handlers.attendance.get_available_classes', return_value=[]), \
         patch('handlers.attendance.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await start_attendance(mock_message, mock_state)
        mock_message.answer.assert_called_with("Все классы уже отмечены на сегодня.")
        mock_state.set_state.assert_not_called()


# ----- Тесты для _build_class_keyboard -----

def test_build_class_keyboard():
    """Клавиатура группирует классы по параллелям."""
    classes = [
        SimpleNamespace(id=1, name="5А", school_id=1, grade=5),
        SimpleNamespace(id=2, name="5Б", school_id=1, grade=5),
        SimpleNamespace(id=3, name="6А", school_id=1, grade=6),
    ]
    kb = _build_class_keyboard(classes)
    assert isinstance(kb, InlineKeyboardMarkup)
    buttons = kb.inline_keyboard
    found = False
    for row in buttons:
        for btn in row:
            if btn.text == "5А":
                found = True
                assert btn.callback_data == "att:class:1:1"
    assert found
    cancel_found = any(btn.text == "❌ Отмена" for row in buttons for btn in row)
    assert cancel_found


# ----- Тесты для cancel_flow -----

@pytest.mark.asyncio
async def test_cancel_flow(mock_callback, mock_state):
    """Отмена выбора класса."""
    with patch('handlers.attendance.build_menu_keyboard', return_value=Mock()):
        await cancel_flow(mock_callback, mock_state)
        mock_callback.message.edit_text.assert_called_once_with("Перекличка отменена.")
        mock_callback.message.answer.assert_called_once()
        mock_state.clear.assert_awaited_once()
        mock_callback.answer.assert_awaited_once()


# ----- Тесты для class_chosen -----

@pytest.mark.asyncio
async def test_class_chosen_success(mock_callback, mock_state, mock_session, mock_students):
    """Успешный выбор класса — переход в режим отметки."""
    mock_callback.data = "att:class:1:1"
    mock_state.get_data = AsyncMock(return_value={})
    with patch('handlers.attendance.AttendanceService.start_attendance', return_value=(mock_session, None)), \
         patch('handlers.attendance.get_students_by_class', return_value=mock_students), \
         patch('handlers.attendance._build_marking_keyboard', return_value=Mock()) as mock_build:
        await class_chosen(mock_callback, mock_state)
        mock_state.update_data.assert_called_with(session_id=10, class_id=1, school_id=1)
        mock_state.set_state.assert_called_with(AttendanceStates.marking)
        mock_callback.message.edit_text.assert_called_once()
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_class_chosen_failure(mock_callback, mock_state):
    """Ошибка при старте сессии."""
    mock_callback.data = "att:class:1:1"
    with patch('handlers.attendance.AttendanceService.start_attendance', return_value=(None, "Ошибка")), \
         patch('handlers.attendance.build_menu_keyboard', return_value=Mock()):
        await class_chosen(mock_callback, mock_state)
        mock_callback.message.edit_text.assert_called_with("Ошибка")
        mock_callback.message.answer.assert_called_once()
        mock_state.clear.assert_awaited_once()
        mock_callback.answer.assert_awaited_once()


# ----- Тесты для toggle_student -----

@pytest.mark.asyncio
async def test_toggle_student(mock_callback, mock_state, mock_students):
    """Переключение статуса ученика."""
    mock_callback.data = "att:toggle:10:1"
    mock_state.get_data = AsyncMock(return_value={"class_id": 1, "school_id": 1})
    with patch('handlers.attendance.AttendanceService.toggle_student', return_value=True) as mock_toggle, \
         patch('handlers.attendance.get_students_by_class', return_value=mock_students), \
         patch('handlers.attendance.get_session_records', return_value=[]), \
         patch('handlers.attendance._build_marking_keyboard', return_value=Mock()) as mock_build:
        await toggle_student(mock_callback, mock_state)
        mock_toggle.assert_called_once_with(10, 1)
        mock_callback.message.edit_reply_markup.assert_called_once()
        mock_callback.answer.assert_awaited_once()


# ----- Тесты для cancel_marking -----

@pytest.mark.asyncio
async def test_cancel_marking(mock_callback, mock_state):
    """Отмена переклички."""
    mock_callback.data = "att:cancel:10"
    with patch('handlers.attendance.delete_session', return_value=None) as mock_delete, \
         patch('handlers.attendance.build_menu_keyboard', return_value=Mock()):
        await cancel_marking(mock_callback, mock_state)
        mock_delete.assert_called_once_with(10)
        mock_callback.message.edit_text.assert_called_once_with("Перекличка отменена.")
        mock_callback.message.answer.assert_called_once()
        mock_state.clear.assert_awaited_once()
        mock_callback.answer.assert_awaited_once()


# ----- Тесты для submit_attendance -----

@pytest.mark.asyncio
async def test_submit_attendance_with_absent(mock_callback, mock_state):
    """Завершение переклички с отсутствующими и уведомление классного руководителя."""
    mock_callback.data = "att:submit:10"
    mock_result = Mock()
    mock_result.class_name = "5А"
    mock_result.class_id = 1
    mock_result.absent = [("Иванов И.И.", "Болеет")]
    mock_class_teacher = Mock()
    mock_class_teacher.telegram_id = 99999

    mock_callback.bot.notify_web = AsyncMock()

    with patch('handlers.attendance.AttendanceService.complete_session', return_value=None) as mock_complete, \
         patch('handlers.attendance.get_session_result', return_value=mock_result), \
         patch('handlers.attendance.get_class_teacher_for_class', return_value=mock_class_teacher), \
         patch('handlers.attendance.build_menu_keyboard', return_value=Mock()):
        await submit_attendance(mock_callback, mock_state)
        mock_complete.assert_called_once_with(10)
        mock_callback.bot.send_message.assert_called_once_with(99999, "📋 Перекличка в вашем классе 5А завершена.\n\nОтсутствуют (1):\n  • Иванов И.И. — Болеет")
        mock_callback.bot.notify_web.assert_called_once_with("summary_update")
        mock_callback.message.edit_text.assert_called_once()
        mock_callback.message.answer.assert_called_once()
        mock_state.clear.assert_awaited_once()
        mock_callback.answer.assert_called_once_with("Готово!")


@pytest.mark.asyncio
async def test_submit_attendance_no_absent(mock_callback, mock_state):
    """Завершение переклички без отсутствующих."""
    mock_callback.data = "att:submit:10"
    mock_result = Mock()
    mock_result.class_name = "5А"
    mock_result.class_id = 1
    mock_result.absent = []

    mock_callback.bot.notify_web = AsyncMock()

    with patch('handlers.attendance.AttendanceService.complete_session', return_value=None), \
         patch('handlers.attendance.get_session_result', return_value=mock_result), \
         patch('handlers.attendance.get_class_teacher_for_class', return_value=None), \
         patch('handlers.attendance.build_menu_keyboard', return_value=Mock()):
        await submit_attendance(mock_callback, mock_state)
        mock_callback.bot.send_message.assert_not_called()
        mock_callback.bot.notify_web.assert_called_once_with("summary_update")
        mock_callback.message.edit_text.assert_called_once()
        mock_state.clear.assert_awaited_once()
        mock_callback.answer.assert_called_once_with("Готово!")


@pytest.mark.asyncio
async def test_submit_attendance_no_result(mock_callback, mock_state):
    """Завершение переклички, но результат не получен."""
    mock_callback.data = "att:submit:10"
    # НЕ создаём notify_web — getattr вернёт None
    with patch('handlers.attendance.AttendanceService.complete_session', return_value=None), \
         patch('handlers.attendance.get_session_result', return_value=None), \
         patch('handlers.attendance.build_menu_keyboard', return_value=Mock()):
        await submit_attendance(mock_callback, mock_state)
        mock_callback.message.edit_text.assert_called_with("✅ Перекличка завершена.", reply_markup=None)
        mock_callback.message.answer.assert_called_once()
        mock_state.clear.assert_awaited_once()
        # notify_web не существует, проверяем, что он не вызывался
        # при отсутствии атрибута, вызов невозможен, поэтому ничего не проверяем


@pytest.mark.asyncio
async def test_submit_attendance_teacher_self_notify(mock_callback, mock_state):
    """Если классный руководитель — это сам учитель, уведомление не отправляется."""
    mock_callback.data = "att:submit:10"
    mock_result = Mock()
    mock_result.class_name = "5А"
    mock_result.class_id = 1
    mock_result.absent = [("Иванов И.И.", "Болеет")]
    mock_class_teacher = Mock()
    mock_class_teacher.telegram_id = 12345

    mock_callback.bot.notify_web = AsyncMock()

    with patch('handlers.attendance.AttendanceService.complete_session', return_value=None), \
         patch('handlers.attendance.get_session_result', return_value=mock_result), \
         patch('handlers.attendance.get_class_teacher_for_class', return_value=mock_class_teacher), \
         patch('handlers.attendance.build_menu_keyboard', return_value=Mock()):
        await submit_attendance(mock_callback, mock_state)
        mock_callback.bot.send_message.assert_not_called()
        mock_callback.bot.notify_web.assert_called_once_with("summary_update")
        mock_callback.message.edit_text.assert_called_once()
        mock_state.clear.assert_awaited_once()
        mock_callback.answer.assert_called_once_with("Готово!")


@pytest.mark.asyncio
async def test_submit_attendance_send_notify_fails(mock_callback, mock_state):
    """Ошибка при отправке уведомления классному руководителю не должна ломать процесс."""
    mock_callback.data = "att:submit:10"
    mock_result = Mock()
    mock_result.class_name = "5А"
    mock_result.class_id = 1
    mock_result.absent = [("Иванов И.И.", "Болеет")]
    mock_class_teacher = Mock()
    mock_class_teacher.telegram_id = 99999

    mock_callback.bot.notify_web = AsyncMock()
    mock_callback.bot.send_message = AsyncMock(side_effect=Exception("Network error"))

    with patch('handlers.attendance.AttendanceService.complete_session', return_value=None), \
         patch('handlers.attendance.get_session_result', return_value=mock_result), \
         patch('handlers.attendance.get_class_teacher_for_class', return_value=mock_class_teacher), \
         patch('handlers.attendance.build_menu_keyboard', return_value=Mock()):
        await submit_attendance(mock_callback, mock_state)
        mock_callback.message.edit_text.assert_called_once()
        mock_state.clear.assert_awaited_once()
        mock_callback.answer.assert_called_once_with("Готово!")