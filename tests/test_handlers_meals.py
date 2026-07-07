import pytest
from unittest.mock import AsyncMock, Mock, patch, ANY
from aiogram.types import Message, CallbackQuery, User, Chat, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from datetime import date
from types import SimpleNamespace

from handlers.meals import (
    meals_router, meal_menu, _show_meal_markup, toggle_eating,
    change_meal_type, _redraw_meal_message, submit_meal, cancel_meal,
    _notify_chefs_for_class, _meal_type_emoji, _get_state, meal_states
)
from core.keyboards import BTN_MEAL, back_to_menu_btn
from core.roles import Role


# ----- Фикстуры -----

@pytest.fixture
def mock_message():
    msg = AsyncMock(spec=Message)
    msg.from_user = Mock(spec=User)
    msg.from_user.id = 12345
    msg.text = BTN_MEAL
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
    cb.message.chat = Mock(spec=Chat)
    cb.message.chat.id = 67890
    cb.message.delete = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    cb.data = "meal:toggle:1"
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
def mock_meal_item():
    item = Mock()
    item.student_id = 1
    item.name = "Иванов И.И."
    item.meal_type = "paid"
    item.is_eating = True
    return item


@pytest.fixture
def mock_meal_request():
    req = Mock()
    req.class_name = "5А"
    req.items = [
        SimpleNamespace(student_id=1, name="Иванов И.И.", meal_type="paid", is_eating=True),
        SimpleNamespace(student_id=2, name="Петров П.П.", meal_type="free", is_eating=False),
    ]
    return req


# ----- Тесты для _meal_type_emoji -----

def test_meal_type_emoji_paid():
    assert _meal_type_emoji("paid") == "💰"

def test_meal_type_emoji_free():
    assert _meal_type_emoji("free") == "🆓"


# ----- Тесты для meal_menu -----

@pytest.mark.asyncio
async def test_meal_menu_no_access(mock_message):
    """Нет прав доступа."""
    with patch('handlers.meals.check_access', return_value=False):
        await meal_menu(mock_message)
        mock_message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_meal_menu_admin(mock_message):
    """Администратор — сообщение о нереализованной функции."""
    with patch('handlers.meals.check_access', return_value=True), \
         patch('handlers.meals.is_admin', return_value=True):
        await meal_menu(mock_message)
        mock_message.answer.assert_called_once_with("Выберите класс (функция для администратора пока не реализована).")


@pytest.mark.asyncio
async def test_meal_menu_no_teacher(mock_message):
    """Учитель не найден."""
    with patch('handlers.meals.check_access', return_value=True), \
         patch('handlers.meals.is_admin', return_value=False), \
         patch('handlers.meals.get_teacher_by_telegram_id', return_value=None):
        await meal_menu(mock_message)
        mock_message.answer.assert_called_once_with("У вас не указан класс. Обратитесь к администратору.")


@pytest.mark.asyncio
async def test_meal_menu_no_class(mock_message):
    """Учитель без класса."""
    teacher = Mock(class_id=None)
    with patch('handlers.meals.check_access', return_value=True), \
         patch('handlers.meals.is_admin', return_value=False), \
         patch('handlers.meals.get_teacher_by_telegram_id', return_value=teacher):
        await meal_menu(mock_message)
        mock_message.answer.assert_called_once_with("У вас не указан класс. Обратитесь к администратору.")


@pytest.mark.asyncio
async def test_meal_menu_success(mock_message):
    """Успешный вход в меню питания."""
    teacher = Mock()
    teacher.class_id = 5
    teacher.id = 1
    teacher.school_id = 1
    with patch('handlers.meals.check_access', return_value=True), \
         patch('handlers.meals.is_admin', return_value=False), \
         patch('handlers.meals.get_teacher_by_telegram_id', return_value=teacher), \
         patch('handlers.meals._show_meal_markup', new_callable=AsyncMock) as mock_show:
        await meal_menu(mock_message)
        mock_show.assert_awaited_once_with(mock_message, 5, 1, 1, edit=False)


# ----- Тесты для _show_meal_markup -----

@pytest.mark.asyncio
async def test_show_meal_markup_no_items(mock_message):
    """Нет учеников в классе."""
    with patch('handlers.meals.get_or_create_meal_request', return_value=Mock(items=[])):
        await _show_meal_markup(mock_message, 1, 1, 1, edit=False)
        mock_message.answer.assert_called_once()
        assert "В классе нет учеников" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_show_meal_markup_with_items(mock_message, mock_meal_request):
    """Есть ученики — показываем клавиатуру."""
    with patch('handlers.meals.get_or_create_meal_request', return_value=mock_meal_request), \
         patch('handlers.meals.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await _show_meal_markup(mock_message, 1, 1, 1, edit=False)
        mock_message.answer.assert_called_once()
        text = mock_message.answer.call_args[0][0]
        assert "Питание на" in text
        assert "Класс: 5А" in text
        kb = mock_message.answer.call_args[1]["reply_markup"]
        assert isinstance(kb, InlineKeyboardMarkup)
        buttons_texts = []
        for row in kb.inline_keyboard:
            for btn in row:
                buttons_texts.append(btn.text)
        assert "✅ Иванов И.И. (💰)" in buttons_texts or "❌ Иванов И.И. (💰)" in buttons_texts
        assert "✅ Петров П.П. (🆓)" in buttons_texts or "❌ Петров П.П. (🆓)" in buttons_texts
        assert any("✅ Подтвердить" in t for t in buttons_texts)
        assert any("❌ Отмена" in t for t in buttons_texts)


# ----- Тесты для toggle_eating -----

@pytest.mark.asyncio
async def test_toggle_eating_state_exists(mock_callback):
    """Переключение статуса — состояние уже есть."""
    mock_callback.data = "meal:toggle:1"
    state_data = {
        'items': {
            1: SimpleNamespace(student_id=1, is_eating=True, meal_type="paid"),
            2: SimpleNamespace(student_id=2, is_eating=False, meal_type="free"),
        },
        'class_id': 5,
        'teacher_id': 1,
        'school_id': 1,
    }
    chat_id = mock_callback.message.chat.id
    meal_states[chat_id] = state_data
    with patch('handlers.meals._redraw_meal_message', new_callable=AsyncMock) as mock_redraw:
        await toggle_eating(mock_callback)
        assert state_data['items'][1].is_eating is False
        mock_redraw.assert_awaited_once_with(mock_callback.message, state_data)
        mock_callback.answer.assert_awaited_once()
    meal_states.pop(chat_id, None)


@pytest.mark.asyncio
async def test_toggle_eating_state_created(mock_callback, mock_meal_request, mock_teacher):
    """Переключение статуса — состояние создаётся."""
    mock_callback.data = "meal:toggle:1"
    chat_id = mock_callback.message.chat.id
    mock_callback.from_user.id = 12345

    with patch('handlers.meals.get_teacher_by_telegram_id', return_value=mock_teacher), \
         patch('handlers.meals.get_or_create_meal_request', return_value=mock_meal_request), \
         patch('handlers.meals._redraw_meal_message', new_callable=AsyncMock) as mock_redraw:
        await toggle_eating(mock_callback)
        state = meal_states.get(chat_id)
        assert state is not None
        assert 'items' in state
        assert state['class_id'] == 5
        assert state['teacher_id'] == 1
        assert state['school_id'] == 1
        assert state['items'][1].is_eating is False
        mock_redraw.assert_awaited_once()
        mock_callback.answer.assert_awaited_once()
    meal_states.pop(chat_id, None)


@pytest.mark.asyncio
async def test_toggle_eating_no_teacher(mock_callback):
    """Учитель не найден — ошибка и состояние не создаётся."""
    mock_callback.data = "meal:toggle:1"
    chat_id = mock_callback.message.chat.id
    # Удаляем возможное состояние
    meal_states.pop(chat_id, None)
    with patch('handlers.meals.get_teacher_by_telegram_id', return_value=None):
        await toggle_eating(mock_callback)
        mock_callback.answer.assert_called_once_with("Ошибка: нет класса.")
        # Состояние не должно создаться, потому что _get_state вызывается до проверки,
        # но проверка не проходит, и состояние остаётся пустым. В коде _get_state создаёт пустой словарь.
        # Проверяем, что в состоянии нет 'items'
        state = meal_states.get(chat_id, {})
        assert 'items' not in state
    meal_states.pop(chat_id, None)


# ----- Тесты для change_meal_type -----

@pytest.mark.asyncio
async def test_change_meal_type_state_exists(mock_callback):
    """Смена типа питания — состояние уже есть."""
    mock_callback.data = "meal:type:1"
    state_data = {
        'items': {
            1: SimpleNamespace(student_id=1, is_eating=True, meal_type="paid"),
            2: SimpleNamespace(student_id=2, is_eating=False, meal_type="free"),
        },
        'class_id': 5,
        'teacher_id': 1,
        'school_id': 1,
    }
    chat_id = mock_callback.message.chat.id
    meal_states[chat_id] = state_data
    with patch('handlers.meals.update_student_meal_type') as mock_update, \
         patch('handlers.meals._redraw_meal_message', new_callable=AsyncMock) as mock_redraw:
        await change_meal_type(mock_callback)
        assert state_data['items'][1].meal_type == "free"
        mock_update.assert_called_once_with(1, "free")
        mock_redraw.assert_awaited_once_with(mock_callback.message, state_data)
        mock_callback.answer.assert_awaited_once()
    meal_states.pop(chat_id, None)


@pytest.mark.asyncio
async def test_change_meal_type_state_created(mock_callback, mock_meal_request, mock_teacher):
    """Смена типа питания — состояние создаётся."""
    mock_callback.data = "meal:type:1"
    chat_id = mock_callback.message.chat.id
    mock_callback.from_user.id = 12345

    with patch('handlers.meals.get_teacher_by_telegram_id', return_value=mock_teacher), \
         patch('handlers.meals.get_or_create_meal_request', return_value=mock_meal_request), \
         patch('handlers.meals.update_student_meal_type') as mock_update, \
         patch('handlers.meals._redraw_meal_message', new_callable=AsyncMock) as mock_redraw:
        await change_meal_type(mock_callback)
        state = meal_states.get(chat_id)
        assert state is not None
        assert state['items'][1].meal_type == "free"
        mock_update.assert_called_once_with(1, "free")
        mock_redraw.assert_awaited_once()
        mock_callback.answer.assert_awaited_once()
    meal_states.pop(chat_id, None)


# ----- Тесты для _redraw_meal_message -----

@pytest.mark.asyncio
async def test_redraw_meal_message(mock_callback):
    """Перерисовка сообщения."""
    state = {
        'items': {
            1: SimpleNamespace(student_id=1, name="Иванов И.И.", is_eating=True, meal_type="paid"),
            2: SimpleNamespace(student_id=2, name="Петров П.П.", is_eating=False, meal_type="free"),
        }
    }
    await _redraw_meal_message(mock_callback.message, state)
    mock_callback.message.edit_reply_markup.assert_called_once()
    kb = mock_callback.message.edit_reply_markup.call_args[1]["reply_markup"]
    assert isinstance(kb, InlineKeyboardMarkup)
    buttons_texts = []
    for row in kb.inline_keyboard:
        for btn in row:
            buttons_texts.append(btn.text)
    assert "✅ Иванов И.И. (💰)" in buttons_texts
    assert "❌ Петров П.П. (🆓)" in buttons_texts


# ----- Тесты для submit_meal -----

@pytest.mark.asyncio
async def test_submit_meal_no_state(mock_callback):
    """Нет состояния — ничего не делаем."""
    chat_id = mock_callback.message.chat.id
    # Удаляем состояние, если есть
    meal_states.pop(chat_id, None)
    await submit_meal(mock_callback)
    mock_callback.answer.assert_called_once_with("Нет изменений.")
    mock_callback.message.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_submit_meal_success_new(mock_callback):
    """Успешное сохранение заявки (новая)."""
    chat_id = mock_callback.message.chat.id
    # state['items'] должен быть словарём
    state_data = {
        'items': {
            1: SimpleNamespace(student_id=1, name="Иванов И.И.", meal_type="paid", is_eating=True),
            2: SimpleNamespace(student_id=2, name="Петров П.П.", meal_type="free", is_eating=False),
        },
        'class_id': 5,
        'teacher_id': 1,
        'school_id': 1,
    }
    meal_states[chat_id] = state_data
    mock_callback.bot.notify_web = AsyncMock()

    with patch('handlers.meals.is_meal_request_exists', return_value=False), \
         patch('handlers.meals.save_meal_request') as mock_save, \
         patch('handlers.meals._notify_chefs_for_class', new_callable=AsyncMock) as mock_notify:
        await submit_meal(mock_callback)
        # items передаются как список значений словаря
        expected_items = list(state_data['items'].values())
        mock_save.assert_called_once_with(5, 1, expected_items, school_id=1)
        mock_notify.assert_not_awaited()
        mock_callback.bot.notify_web.assert_called_once_with("meals_update", {"school_id": 1})
        mock_callback.message.edit_text.assert_called_once_with("✅ Заявка на питание отправлена.", reply_markup=None)
        mock_callback.answer.assert_called_once_with("Отправлено!")
        assert chat_id not in meal_states


@pytest.mark.asyncio
async def test_submit_meal_success_existing(mock_callback):
    """Успешное сохранение заявки (существующая — отправляем уведомление поварам)."""
    chat_id = mock_callback.message.chat.id
    state_data = {
        'items': {
            1: SimpleNamespace(student_id=1, name="Иванов И.И.", meal_type="paid", is_eating=True),
            2: SimpleNamespace(student_id=2, name="Петров П.П.", meal_type="free", is_eating=False),
        },
        'class_id': 5,
        'teacher_id': 1,
        'school_id': 1,
    }
    meal_states[chat_id] = state_data
    mock_callback.bot.notify_web = AsyncMock()

    with patch('handlers.meals.is_meal_request_exists', return_value=True), \
         patch('handlers.meals.save_meal_request') as mock_save, \
         patch('handlers.meals._notify_chefs_for_class', new_callable=AsyncMock) as mock_notify:
        await submit_meal(mock_callback)
        expected_items = list(state_data['items'].values())
        mock_save.assert_called_once_with(5, 1, expected_items, school_id=1)
        mock_notify.assert_awaited_once_with(mock_callback.bot, 5, 1)
        mock_callback.bot.notify_web.assert_called_once_with("meals_update", {"school_id": 1})
        mock_callback.message.edit_text.assert_called_once_with("✅ Заявка на питание отправлена.", reply_markup=None)
        mock_callback.answer.assert_called_once_with("Отправлено!")
        assert chat_id not in meal_states


@pytest.mark.asyncio
async def test_submit_meal_no_school_id(mock_callback, mock_teacher):
    """Нет school_id в состоянии — берём из учителя."""
    chat_id = mock_callback.message.chat.id
    mock_callback.from_user.id = 12345
    state_data = {
        'items': {
            1: SimpleNamespace(student_id=1, name="Иванов И.И.", meal_type="paid", is_eating=True),
        },
        'class_id': 5,
        'teacher_id': 1,
        # school_id отсутствует
    }
    meal_states[chat_id] = state_data
    mock_callback.bot.notify_web = AsyncMock()

    with patch('handlers.meals.get_teacher_by_telegram_id', return_value=mock_teacher), \
         patch('handlers.meals.is_meal_request_exists', return_value=False), \
         patch('handlers.meals.save_meal_request') as mock_save:
        await submit_meal(mock_callback)
        expected_items = list(state_data['items'].values())
        mock_save.assert_called_once_with(5, 1, expected_items, school_id=1)
        mock_callback.bot.notify_web.assert_called_once_with("meals_update", {"school_id": 1})
        assert chat_id not in meal_states


# ----- Тесты для cancel_meal -----

@pytest.mark.asyncio
async def test_cancel_meal(mock_callback):
    """Отмена заявки."""
    chat_id = mock_callback.message.chat.id
    meal_states[chat_id] = {'items': {}}
    await cancel_meal(mock_callback)
    assert chat_id not in meal_states
    mock_callback.message.edit_text.assert_called_once_with("Питание отменено.", reply_markup=None)
    mock_callback.answer.assert_awaited_once()


# ----- Тесты для _notify_chefs_for_class -----

@pytest.mark.asyncio
async def test_notify_chefs_for_class_no_chefs(mock_callback):
    """Нет шеф-поваров — уведомления не отправляются."""
    with patch('handlers.meals.get_chef_telegram_ids', return_value=[]):
        await _notify_chefs_for_class(mock_callback.bot, 1, 1)
        mock_callback.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_chefs_for_class_success(mock_callback):
    """Успешное уведомление шеф-поваров."""
    chef_ids = [100, 200]
    with patch('handlers.meals.get_chef_telegram_ids', return_value=chef_ids), \
         patch('handlers.meals.get_class_meal_summary', return_value="Summary text"):
        await _notify_chefs_for_class(mock_callback.bot, 1, 1)
        assert mock_callback.bot.send_message.call_count == 2
        mock_callback.bot.send_message.assert_any_call(100, "Summary text")
        mock_callback.bot.send_message.assert_any_call(200, "Summary text")


@pytest.mark.asyncio
async def test_notify_chefs_for_class_send_fails(mock_callback):
    """Ошибка при отправке одному из поваров не ломает процесс."""
    chef_ids = [100, 200]
    mock_callback.bot.send_message = AsyncMock(side_effect=[None, Exception("Network error")])
    with patch('handlers.meals.get_chef_telegram_ids', return_value=chef_ids), \
         patch('handlers.meals.get_class_meal_summary', return_value="Summary text"):
        await _notify_chefs_for_class(mock_callback.bot, 1, 1)
        assert mock_callback.bot.send_message.call_count == 2


# ----- Тесты для _get_state -----

def test_get_state_new():
    """Создание нового состояния."""
    chat_id = 999
    meal_states.pop(chat_id, None)
    state = _get_state(chat_id)
    assert state == {}
    assert chat_id in meal_states
    meal_states.pop(chat_id, None)


def test_get_state_existing():
    """Получение существующего состояния."""
    chat_id = 888
    meal_states[chat_id] = {'test': 'value'}
    state = _get_state(chat_id)
    assert state == {'test': 'value'}
    meal_states.pop(chat_id, None)