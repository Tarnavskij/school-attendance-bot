import pytest
from unittest.mock import AsyncMock, Mock, patch
from aiogram.types import Message, CallbackQuery, User, Chat
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from handlers.registration import registration_router, RegistrationStates, _cancel_registration
from core.keyboards import BTN_REQUEST_ACCESS, access_request_kb
from core.roles import Role
from database import RegistrationRequest
from types import SimpleNamespace


# ----- Фикстуры -----

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
    cb.data = "reg:cancel"
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


# ----- Тесты для _cancel_registration -----

@pytest.mark.asyncio
async def test_cancel_registration(mock_message, mock_state):
    """Отмена регистрации очищает состояние и отправляет сообщение."""
    with patch('handlers.registration.access_request_kb', access_request_kb):
        await _cancel_registration(mock_message, mock_state)
        mock_state.clear.assert_awaited_once()
        mock_message.answer.assert_called_once_with(
            "Регистрация отменена. Если захотите попробовать снова — нажмите кнопку ниже.",
            reply_markup=access_request_kb
        )


# ----- Тесты для start_registration -----

@pytest.mark.asyncio
async def test_start_registration_already_registered(mock_message, mock_state):
    """Если пользователь уже зарегистрирован — сообщаем об этом."""
    with patch('handlers.registration.get_teacher_by_telegram_id', return_value=Mock()):
        from handlers.registration import start_registration
        await start_registration(mock_message, mock_state)
        mock_message.answer.assert_called_once_with("Вы уже зарегистрированы. Нажмите /menu.")
        mock_state.clear.assert_not_called()


@pytest.mark.asyncio
async def test_start_registration_has_pending_request(mock_message, mock_state):
    """Если есть pending-заявка — сообщаем."""
    with patch('handlers.registration.get_teacher_by_telegram_id', return_value=None), \
         patch('handlers.registration.get_all_schools', return_value=[{"id": 1, "name": "School"}]), \
         patch('handlers.registration.has_pending_request', return_value=True):
        from handlers.registration import start_registration
        await start_registration(mock_message, mock_state)
        mock_message.answer.assert_called_once_with(
            "Вы уже подали заявку и она ожидает рассмотрения. "
            "Как только администратор примет решение, вы получите доступ."
        )
        mock_state.clear.assert_not_called()


@pytest.mark.asyncio
async def test_start_registration_new(mock_message, mock_state):
    """Новый пользователь начинает регистрацию."""
    with patch('handlers.registration.get_teacher_by_telegram_id', return_value=None), \
         patch('handlers.registration.get_all_schools', return_value=[]), \
         patch('handlers.registration.has_pending_request', return_value=False):
        from handlers.registration import start_registration
        await start_registration(mock_message, mock_state)
        mock_state.clear.assert_awaited_once()
        mock_state.set_state.assert_called_once_with(RegistrationStates.waiting_name)
        mock_message.answer.assert_called_once()
        assert "Шаг 1 из 3" in mock_message.answer.call_args[0][0]


# ----- Тесты для process_name -----

@pytest.mark.asyncio
async def test_process_name_valid(mock_message, mock_state):
    """Валидное имя переводит на фамилию."""
    mock_message.text = "Иван"
    with patch('handlers.registration._validate_name_part', return_value=True):
        from handlers.registration import process_name
        await process_name(mock_message, mock_state)
        mock_state.update_data.assert_called_once_with(name="Иван")
        mock_state.set_state.assert_called_once_with(RegistrationStates.waiting_surname)
        mock_message.answer.assert_called_once()
        assert "фамилию" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_process_name_invalid(mock_message, mock_state):
    """Невалидное имя — повторный запрос."""
    mock_message.text = "123"
    with patch('handlers.registration._validate_name_part', return_value=False):
        from handlers.registration import process_name
        await process_name(mock_message, mock_state)
        mock_state.update_data.assert_not_called()
        mock_state.set_state.assert_not_called()
        mock_message.answer.assert_called_once_with(
            "Пожалуйста, введите настоящее имя:\n"
            "• только буквы (русские или латинские), дефис и апостроф\n"
            "• от 2 до 30 символов\n"
            "• без цифр, пробелов, эмодзи и спецсимволов"
        )


# ----- Тесты для process_surname -----

@pytest.mark.asyncio
async def test_process_surname_valid(mock_message, mock_state):
    """Валидная фамилия переводит на выбор роли."""
    mock_message.text = "Петров"
    with patch('handlers.registration._validate_name_part', return_value=True):
        from handlers.registration import process_surname
        await process_surname(mock_message, mock_state)
        mock_state.update_data.assert_called_once_with(surname="Петров")
        mock_state.set_state.assert_called_once_with(RegistrationStates.choosing_role)
        mock_message.answer.assert_called_once()
        assert "роль" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_process_surname_invalid(mock_message, mock_state):
    """Невалидная фамилия — повторный запрос."""
    mock_message.text = "123"
    with patch('handlers.registration._validate_name_part', return_value=False):
        from handlers.registration import process_surname
        await process_surname(mock_message, mock_state)
        mock_state.update_data.assert_not_called()
        mock_state.set_state.assert_not_called()
        mock_message.answer.assert_called_once_with(
            "Пожалуйста, введите настоящую фамилию:\n"
            "• только буквы (русские или латинские), дефис и апостроф\n"
            "• от 2 до 30 символов\n"
            "• без цифр, пробелов, эмодзи и спецсимволов"
        )


# ----- Тесты для role_chosen -----

@pytest.mark.asyncio
async def test_role_chosen_class_teacher(mock_callback, mock_state):
    """Выбор роли 'классный руководитель' — переходим к выбору класса."""
    mock_callback.data = "reg:role:class_teacher"
    with patch('handlers.registration.get_all_schools', return_value=[{"id": 1, "name": "School"}]), \
         patch('handlers.registration.get_all_classes', return_value=[Mock(id=1, name="5A")]), \
         patch('handlers.registration._proceed_after_school', new_callable=AsyncMock):
        from handlers.registration import role_chosen
        await role_chosen(mock_callback, mock_state)
        # Проверяем, что update_data вызван дважды: с role и с school_id
        mock_state.update_data.assert_any_call(role=Role.CLASS_TEACHER)
        mock_state.update_data.assert_any_call(school_id=1)
        mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_role_chosen_subject_teacher(mock_callback, mock_state):
    """Выбор роли 'учитель-предметник' — переходим к выбору школы (или сразу к _proceed_after_school)."""
    mock_callback.data = "reg:role:subject_teacher"
    with patch('handlers.registration.get_all_schools', return_value=[{"id": 1, "name": "School"}]), \
         patch('handlers.registration._proceed_after_school', new_callable=AsyncMock):
        from handlers.registration import role_chosen
        await role_chosen(mock_callback, mock_state)
        mock_state.update_data.assert_any_call(role=Role.SUBJECT_TEACHER)
        mock_state.update_data.assert_any_call(school_id=1)
        mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_role_chosen_invalid(mock_callback, mock_state):
    """Неверная роль — ошибка."""
    mock_callback.data = "reg:role:invalid"
    from handlers.registration import role_chosen
    await role_chosen(mock_callback, mock_state)
    mock_callback.answer.assert_called_once_with("Неверный выбор, попробуйте ещё раз.", show_alert=True)
    mock_state.update_data.assert_not_called()


# ----- Тесты для school_chosen -----

@pytest.mark.asyncio
async def test_school_chosen(mock_callback, mock_state):
    """Выбор школы — передаём управление _proceed_after_school."""
    mock_callback.data = "reg:school:1"
    with patch('handlers.registration._proceed_after_school', new_callable=AsyncMock) as mock_proceed:
        from handlers.registration import school_chosen
        await school_chosen(mock_callback, mock_state)
        mock_state.update_data.assert_called_once_with(school_id=1)
        mock_callback.answer.assert_called_once()
        mock_proceed.assert_awaited_once_with(mock_callback, mock_state, Role.SUBJECT_TEACHER)  # role по умолчанию


# ----- Тесты для class_chosen -----

@pytest.mark.asyncio
async def test_class_chosen(mock_callback, mock_state):
    """Выбор класса — сохраняем заявку и уведомляем администратора."""
    mock_callback.data = "reg:class:1"
    mock_state.get_data = AsyncMock(return_value={"school_id": 1})
    with patch('handlers.registration._save_and_notify', new_callable=AsyncMock, return_value=True) as mock_save:
        from handlers.registration import class_chosen
        await class_chosen(mock_callback, mock_state)
        mock_callback.answer.assert_called_once()
        mock_save.assert_awaited_once_with(12345, mock_state, mock_callback.bot, class_id=1, school_id=1)
        mock_callback.message.edit_text.assert_called_once()
        assert "Заявка отправлена" in mock_callback.message.edit_text.call_args[0][0]


# ----- Тесты для _proceed_after_school -----

@pytest.mark.asyncio
async def test_proceed_after_school_class_teacher_no_classes(mock_callback, mock_state):
    """Классный руководитель, но нет классов — ошибка."""
    with patch('handlers.registration.get_all_classes', return_value=[]):
        from handlers.registration import _proceed_after_school
        await _proceed_after_school(mock_callback, mock_state, Role.CLASS_TEACHER)
        mock_callback.message.edit_text.assert_called_once()
        assert "нет ни одного класса" in mock_callback.message.edit_text.call_args[0][0]
        mock_state.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_proceed_after_school_class_teacher_with_classes(mock_callback, mock_state):
    """Классный руководитель — показываем список классов."""
    # Создаём объекты с реальными строками
    class_5a = SimpleNamespace(id=1, name="5A")
    class_5b = SimpleNamespace(id=2, name="5B")
    mock_classes = [class_5a, class_5b]
    with patch('handlers.registration.get_all_classes', return_value=mock_classes):
        from handlers.registration import _proceed_after_school
        await _proceed_after_school(mock_callback, mock_state, Role.CLASS_TEACHER)
        mock_state.set_state.assert_called_once_with(RegistrationStates.choosing_class)
        mock_callback.message.edit_text.assert_called_once()
        assert "выберите ваш класс" in mock_callback.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_proceed_after_school_non_class_teacher(mock_callback, mock_state):
    """Учитель-предметник или секретарь — сохраняем заявку."""
    mock_state.get_data = AsyncMock(return_value={"school_id": 1, "name": "Иван", "surname": "Петров", "role": Role.SUBJECT_TEACHER})
    with patch('handlers.registration._save_and_notify', new_callable=AsyncMock, return_value=True) as mock_save:
        from handlers.registration import _proceed_after_school
        await _proceed_after_school(mock_callback, mock_state, Role.SUBJECT_TEACHER)
        mock_save.assert_awaited_once_with(12345, mock_state, mock_callback.bot, class_id=None, school_id=1)
        mock_callback.message.edit_text.assert_called_once()
        assert "Заявка отправлена" in mock_callback.message.edit_text.call_args[0][0]
        mock_state.clear.assert_awaited_once()


# ----- Тесты для _save_and_notify -----

@pytest.mark.asyncio
async def test_save_and_notify_success(mock_callback, mock_state):
    """Успешное сохранение заявки и уведомление админа."""
    mock_state.get_data = AsyncMock(return_value={"name": "Иван", "surname": "Петров", "role": Role.SUBJECT_TEACHER})
    with patch('handlers.registration.has_pending_request', return_value=False), \
         patch('handlers.registration.SessionLocal') as mock_db_class, \
         patch('handlers.registration.get_all_schools', return_value=[{"id": 1, "name": "School"}]):
        # Мокаем сессию БД
        mock_db = Mock()
        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.close = Mock()
        mock_db_class.return_value = mock_db

        from handlers.registration import _save_and_notify
        result = await _save_and_notify(12345, mock_state, mock_callback.bot, class_id=None, school_id=1)
        assert result is True
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_callback.bot.send_message.assert_called_once()
        assert "Новая заявка" in mock_callback.bot.send_message.call_args[0][1]


@pytest.mark.asyncio
async def test_save_and_notify_already_pending(mock_callback, mock_state):
    """Если заявка уже существует — возвращаем False."""
    with patch('handlers.registration.has_pending_request', return_value=True):
        from handlers.registration import _save_and_notify
        result = await _save_and_notify(12345, mock_state, mock_callback.bot, class_id=None, school_id=1)
        assert result is False
        mock_callback.bot.send_message.assert_not_called()


# ----- Тесты для отмены -----

@pytest.mark.asyncio
async def test_cancel_inline(mock_callback, mock_state):
    """Отмена через inline-кнопку."""
    from handlers.registration import cancel_inline
    await cancel_inline(mock_callback, mock_state)
    mock_state.clear.assert_awaited_once()
    mock_callback.message.edit_text.assert_called_once_with("Регистрация отменена.")
    mock_callback.message.answer.assert_called_once()
    mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_on_command_during_name(mock_message, mock_state):
    """Команда /start или /menu во время ввода имени отменяет регистрацию."""
    from handlers.registration import cancel_on_command
    await cancel_on_command(mock_message, mock_state)
    mock_state.clear.assert_awaited_once()
    mock_message.answer.assert_called_once()
    assert "Регистрация отменена" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cancel_on_text_during_inline(mock_message, mock_state):
    """Любой текст во время выбора школы/класса отменяет регистрацию."""
    from handlers.registration import cancel_on_text_during_inline
    await cancel_on_text_during_inline(mock_message, mock_state)
    mock_state.clear.assert_awaited_once()
    mock_message.answer.assert_called_once()
    assert "Регистрация отменена" in mock_message.answer.call_args[0][0]