import pytest
from unittest.mock import AsyncMock, Mock, patch, ANY
from aiogram.types import Message, CallbackQuery, User, Chat, InlineKeyboardMarkup, BufferedInputFile
from aiogram.fsm.context import FSMContext
from datetime import date
from types import SimpleNamespace
from io import BytesIO
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="openpyxl")


from handlers.admin import (
    admin_router,
    AddStudentStates,
    school_summary,
    download_excel,
    reset_confirm,
    reset_cancel,
    reset_execute,
    _build_excel,
    teacher_list,
    teachers_page_callback,
    _show_teacher_page,
    _teacher_list_keyboard,
    noop,
    back_to_teacher_list,
    show_requests,
    request_detail,
    approve_request_handler,
    reject_request_handler,
    teacher_card,
    _show_teacher_card,
    permanent_delete_confirm,
    permanent_delete_execute,
    remove_class,
    change_role_menu,
    set_role,
    set_class_menu,
    assign_class,
    students_menu,
    _show_classes_for_students,
    show_students,
    students_page_callback,
    _show_student_page,
    back_to_classes,
    add_student_start,
    process_student_name,
    delete_student_confirm,
    delete_student_execute,
    list_schools,
    switch_school,
    restore_admin,
)
from core.keyboards import (
    BTN_SCHOOL_SUMMARY,
    BTN_TEACHER_LIST,
    BTN_STUDENTS,
    BTN_SCHOOLS,
    build_menu_keyboard,
)
from core.roles import Role, ROLE_LABELS
from config import ADMIN_TELEGRAM_ID


# ----- Фикстуры -----

@pytest.fixture
def mock_message():
    msg = AsyncMock(spec=Message)
    msg.from_user = Mock(spec=User)
    msg.from_user.id = ADMIN_TELEGRAM_ID
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
    cb.from_user.id = ADMIN_TELEGRAM_ID
    cb.message = AsyncMock(spec=Message)
    cb.message.delete = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer_document = AsyncMock()
    cb.answer = AsyncMock()
    cb.data = "admin:excel"
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
    t = Mock()
    t.id = 1
    t.telegram_id = 123456789
    t.name = "Иван Иванов"
    t.role = "subject_teacher"
    t.is_active = True
    t.school_id = 1
    t.class_id = None
    t.class_name = None
    t.school_name = "Основная школа"
    return t


@pytest.fixture
def mock_request():
    return {
        'id': 1,
        'telegram_id': 999,
        'name': 'Петров П.П.',
        'role': 'subject_teacher',
        'role_label': 'Учитель-предметник',
        'class_name': '5А',
    }


@pytest.fixture
def mock_student():
    s = Mock()
    s.id = 1
    s.name = "Сидоров С.С."
    return s


@pytest.fixture
def mock_class():
    c = Mock()
    c.id = 1
    c.name = "5А"
    return c


# ----- Тесты для school_summary -----

@pytest.mark.asyncio
async def test_school_summary_success(mock_message):
    """Успешный показ сводки."""
    mock_summary = "Сводка за сегодня"
    with patch('handlers.admin.ReportService.get_daily_summary', return_value=mock_summary), \
         patch('handlers.admin.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await school_summary(mock_message)
        mock_message.answer.assert_called_once()
        args = mock_message.answer.call_args[0][0]
        assert args == mock_summary
        kb = mock_message.answer.call_args[1]["reply_markup"]
        assert isinstance(kb, InlineKeyboardMarkup)


# ----- Тесты для download_excel -----

@pytest.mark.asyncio
async def test_download_excel_success(mock_callback):
    """Успешная загрузка Excel."""
    mock_callback.data = "admin:excel"
    mock_sessions = []
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.get_sessions_for_report', return_value=mock_sessions), \
         patch('handlers.admin._build_excel', return_value=b"test"), \
         patch('handlers.admin.date') as mock_date:
        mock_date.today = Mock(return_value=date(2026, 7, 7))
        await download_excel(mock_callback)
        mock_callback.answer.assert_called_once_with("Формирую файл…")
        mock_callback.message.answer_document.assert_called_once()


@pytest.mark.asyncio
async def test_download_excel_not_admin(mock_callback):
    """Не админ — игнорируем."""
    mock_callback.data = "admin:excel"
    with patch('handlers.admin.is_admin', return_value=False):
        await download_excel(mock_callback)
        mock_callback.answer.assert_not_called()


# ----- Тесты для reset_confirm, reset_cancel, reset_execute -----

@pytest.mark.asyncio
async def test_reset_confirm_success(mock_callback):
    """Подтверждение сброса."""
    mock_callback.data = "admin:reset_confirm"
    with patch('handlers.admin.is_admin', return_value=True):
        await reset_confirm(mock_callback)
        mock_callback.message.edit_text.assert_called_once()
        assert "Сбросить все перекличи" in mock_callback.message.edit_text.call_args[0][0]
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_cancel_success(mock_callback):
    """Отмена сброса."""
    mock_callback.data = "admin:reset_cancel"
    mock_summary = "Сводка"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.ReportService.get_daily_summary', return_value=mock_summary), \
         patch('handlers.admin.date') as mock_date:
        mock_date.today = Mock(return_value=date.today())
        await reset_cancel(mock_callback)
        mock_callback.message.edit_text.assert_called_once_with(mock_summary, reply_markup=ANY)
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_execute_success(mock_callback):
    """Выполнение сброса."""
    mock_callback.data = "admin:reset_execute"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.reset_today_sessions', return_value=3), \
         patch('handlers.admin.build_menu_keyboard', return_value=Mock()):
        await reset_execute(mock_callback)
        mock_callback.message.edit_text.assert_called_once()
        assert "Сброс выполнен" in mock_callback.message.edit_text.call_args[0][0]
        mock_callback.message.answer.assert_called_once()
        mock_callback.answer.assert_awaited_once()


# ----- Тесты для _build_excel -----

def test_build_excel():
    """Создание Excel-файла."""
    mock_session = Mock()
    mock_session.teacher_name = "Иванов"
    mock_session.class_name = "5А"
    mock_session.absent = [("Петров", "Болеет")]
    mock_session.end_time = None
    result = _build_excel([mock_session], "2026-07-07")
    assert isinstance(result, bytes)
    assert len(result) > 0


# ----- Тесты для teacher_list и пагинация -----

@pytest.mark.asyncio
async def test_teacher_list_success(mock_message):
    """Показ списка учителей."""
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin._show_teacher_page', new_callable=AsyncMock) as mock_show:
        await teacher_list(mock_message)
        mock_show.assert_awaited_once_with(mock_message, page=1)


@pytest.mark.asyncio
async def test_teachers_page_callback_success(mock_callback):
    """Переключение страницы учителей."""
    mock_callback.data = "admin:teachers_page:2"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin._show_teacher_page', new_callable=AsyncMock) as mock_show:
        await teachers_page_callback(mock_callback)
        mock_show.assert_awaited_once_with(mock_callback.message, page=2, edit=True)
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_show_teacher_page_success(mock_message):
    """Отображение страницы учителей."""
    mock_teachers = [Mock()]
    mock_total = 1
    with patch('handlers.admin.get_teachers_paginated', return_value=(mock_teachers, mock_total)), \
         patch('handlers.admin._teacher_list_keyboard', return_value=Mock()):
        await _show_teacher_page(mock_message, page=1, edit=False)
        mock_message.answer.assert_called_once()
        assert "Управление пользователями" in mock_message.answer.call_args[0][0]


def test_teacher_list_keyboard():
    """Формирование клавиатуры списка учителей."""
    mock_teacher = Mock()
    mock_teacher.is_active = True
    mock_teacher.name = "Иванов"
    mock_teacher.role = "subject_teacher"
    mock_teacher.class_name = "5А"
    mock_teacher.school_name = "Основная школа"
    mock_teacher.id = 1
    kb = _teacher_list_keyboard([mock_teacher], 1, 1)
    assert isinstance(kb, InlineKeyboardMarkup)
    buttons = kb.inline_keyboard
    found = False
    for row in buttons:
        for btn in row:
            if btn.text.startswith("🟢 Иванов"):
                found = True
                assert btn.callback_data == "admin:teacher:1"
    assert found


@pytest.mark.asyncio
async def test_noop(mock_callback):
    """Пустой колбэк."""
    await noop(mock_callback)
    mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_back_to_teacher_list(mock_callback):
    """Возврат к списку учителей."""
    mock_callback.data = "admin:back_teachers"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin._show_teacher_page', new_callable=AsyncMock) as mock_show:
        await back_to_teacher_list(mock_callback)
        mock_show.assert_awaited_once_with(mock_callback.message, page=1, edit=True)
        mock_callback.answer.assert_awaited_once()


# ----- Тесты для заявок -----

@pytest.mark.asyncio
async def test_show_requests_empty(mock_callback):
    """Нет заявок."""
    mock_callback.data = "admin:requests"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.get_pending_requests', return_value=[]):
        await show_requests(mock_callback)
        mock_callback.message.edit_text.assert_called_once()
        assert "Нет активных заявок" in mock_callback.message.edit_text.call_args[0][0]
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_show_requests_with_requests(mock_callback, mock_request):
    """Есть заявки."""
    mock_callback.data = "admin:requests"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.get_pending_requests', return_value=[mock_request]):
        await show_requests(mock_callback)
        mock_callback.message.edit_text.assert_called_once()
        assert "Активные заявки" in mock_callback.message.edit_text.call_args[0][0]
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_detail_found(mock_callback, mock_request):
    """Детали заявки найдены."""
    mock_callback.data = "admin:request:1"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.get_pending_requests', return_value=[mock_request]):
        await request_detail(mock_callback)
        mock_callback.message.edit_text.assert_called_once()
        assert "Заявка от Петров П.П." in mock_callback.message.edit_text.call_args[0][0]
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_detail_not_found(mock_callback):
    """Заявка не найдена."""
    mock_callback.data = "admin:request:999"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.get_pending_requests', return_value=[]):
        await request_detail(mock_callback)
        mock_callback.answer.assert_called_once_with("Заявка не найдена.")


@pytest.mark.asyncio
async def test_approve_request_handler_success(mock_callback):
    """Одобрение заявки."""
    mock_callback.data = "admin:approve:1"
    mock_callback.bot.notify_web = AsyncMock()
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.approve_request', return_value=True):
        await approve_request_handler(mock_callback)
        mock_callback.answer.assert_called_once_with("✅ Заявка одобрена, пользователь добавлен.")
        mock_callback.bot.notify_web.assert_awaited_once_with("requests_update")


@pytest.mark.asyncio
async def test_reject_request_handler(mock_callback):
    """Отклонение заявки."""
    mock_callback.data = "admin:reject:1"
    mock_callback.bot.notify_web = AsyncMock()
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.reject_request') as mock_reject:
        await reject_request_handler(mock_callback)
        mock_reject.assert_called_once_with(1)
        mock_callback.answer.assert_called_once_with("Заявка отклонена.")
        mock_callback.bot.notify_web.assert_awaited_once_with("requests_update")


@pytest.mark.asyncio
async def test_approve_request_handler_fail(mock_callback):
    """Одобрение не удалось."""
    mock_callback.data = "admin:approve:1"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.approve_request', return_value=False):
        await approve_request_handler(mock_callback)
        mock_callback.answer.assert_called_once_with("❌ Не удалось одобрить. Пользователь уже активен в этой школе.")


# ----- Тесты для teacher_card -----

@pytest.mark.asyncio
async def test_teacher_card_success(mock_callback, mock_teacher):
    """Карточка учителя."""
    mock_callback.data = "admin:teacher:1"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin._show_teacher_card', new_callable=AsyncMock) as mock_show:
        await teacher_card(mock_callback)
        mock_show.assert_awaited_once_with(mock_callback.message, 1)
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_show_teacher_card_found(mock_message, mock_teacher):
    """Показ карточки учителя (найден)."""
    with patch('handlers.admin.get_teacher_card', return_value=mock_teacher):
        await _show_teacher_card(mock_message, 1)
        mock_message.edit_text.assert_called_once()
        assert "Иван Иванов" in mock_message.edit_text.call_args[0][0]
        assert "Учитель-предметник" in mock_message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_show_teacher_card_not_found(mock_message):
    """Учитель не найден."""
    with patch('handlers.admin.get_teacher_card', return_value=None):
        await _show_teacher_card(mock_message, 999)
        mock_message.edit_text.assert_called_once_with("Пользователь не найден.")


# ----- Тесты для действий с учителем (удаление, класс, роль) -----

@pytest.mark.asyncio
async def test_permanent_delete_confirm(mock_callback):
    """Подтверждение удаления."""
    mock_callback.data = "admin:delete_perm:1"
    with patch('handlers.admin.is_admin', return_value=True):
        await permanent_delete_confirm(mock_callback)
        mock_callback.message.edit_text.assert_called_once()
        assert "Удалить пользователя" in mock_callback.message.edit_text.call_args[0][0]
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_permanent_delete_execute_success(mock_callback):
    """Успешное удаление."""
    mock_callback.data = "admin:delete_perm_ok:1"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.delete_teacher', return_value=True), \
         patch('handlers.admin._show_teacher_page', new_callable=AsyncMock) as mock_show:
        await permanent_delete_execute(mock_callback)
        mock_callback.answer.assert_called_once_with("Учитель удалён. История сохранена.")
        mock_show.assert_awaited_once_with(mock_callback.message, page=1, edit=True)


@pytest.mark.asyncio
async def test_permanent_delete_execute_fail(mock_callback):
    """Ошибка удаления."""
    mock_callback.data = "admin:delete_perm_ok:1"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.delete_teacher', return_value=False):
        await permanent_delete_execute(mock_callback)
        mock_callback.answer.assert_called_once_with("Ошибка.")


@pytest.mark.asyncio
async def test_remove_class_success(mock_callback):
    """Снятие класса."""
    mock_callback.data = "admin:rmclass:1"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.update_teacher_class') as mock_update, \
         patch('handlers.admin._show_teacher_card', new_callable=AsyncMock) as mock_show:
        await remove_class(mock_callback)
        mock_update.assert_called_once_with(1, None)
        mock_callback.answer.assert_called_once_with("Класс снят.")
        mock_show.assert_awaited_once_with(mock_callback.message, 1)


@pytest.mark.asyncio
async def test_change_role_menu(mock_callback):
    """Меню смены роли."""
    mock_callback.data = "admin:chrole:1"
    with patch('handlers.admin.is_admin', return_value=True):
        await change_role_menu(mock_callback)
        mock_callback.message.edit_text.assert_called_once()
        assert "Выберите новую роль" in mock_callback.message.edit_text.call_args[0][0]
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_role_success(mock_callback):
    """Установка роли."""
    mock_callback.data = "admin:setrole:1:class_teacher"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.update_teacher_role') as mock_update, \
         patch('handlers.admin._show_teacher_card', new_callable=AsyncMock) as mock_show:
        await set_role(mock_callback)
        mock_update.assert_called_once_with(1, "class_teacher")
        mock_callback.answer.assert_called_once_with("Роль изменена.")
        mock_show.assert_awaited_once_with(mock_callback.message, 1)


@pytest.mark.asyncio
async def test_set_class_menu(mock_callback, mock_class):
    """Меню выбора класса."""
    mock_callback.data = "admin:setclass:1"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.get_all_classes', return_value=[mock_class]):
        await set_class_menu(mock_callback)
        mock_callback.message.edit_text.assert_called_once()
        assert "Выберите класс" in mock_callback.message.edit_text.call_args[0][0]
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_assign_class_success(mock_callback):
    """Назначение класса."""
    mock_callback.data = "admin:assignclass:1:2"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.update_teacher_class') as mock_update, \
         patch('handlers.admin._show_teacher_card', new_callable=AsyncMock) as mock_show:
        await assign_class(mock_callback)
        mock_update.assert_called_once_with(1, 2)
        mock_callback.answer.assert_called_once_with("Класс назначен.")
        mock_show.assert_awaited_once_with(mock_callback.message, 1)


# ----- Тесты для учеников -----

@pytest.mark.asyncio
async def test_students_menu_no_classes(mock_message):
    """Нет классов."""
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.get_all_classes', return_value=[]):
        await students_menu(mock_message)
        mock_message.answer.assert_called_once()
        assert "Нет классов в базе" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_students_menu_with_classes(mock_message, mock_class):
    """Есть классы."""
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.get_all_classes', return_value=[mock_class]):
        await students_menu(mock_message)
        mock_message.answer.assert_called_once()
        assert "Выберите класс" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_show_students_success(mock_callback, mock_student):
    """Показ учеников класса."""
    mock_callback.data = "admin:students:1"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin._show_student_page', new_callable=AsyncMock) as mock_show:
        await show_students(mock_callback)
        mock_show.assert_awaited_once_with(mock_callback.message, 1, page=1)
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_students_page_callback(mock_callback):
    """Пагинация учеников."""
    mock_callback.data = "admin:students_page:1:2"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin._show_student_page', new_callable=AsyncMock) as mock_show:
        await students_page_callback(mock_callback)
        mock_show.assert_awaited_once_with(mock_callback.message, 1, page=2, edit=True)
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_show_student_page(mock_message, mock_student):
    """Отображение страницы учеников."""
    mock_class = Mock()
    mock_class.name = "5А"
    mock_class.id = 1
    with patch('handlers.admin.get_students_by_class_paginated', return_value=([mock_student], 1)), \
         patch('handlers.admin.get_all_classes', return_value=[mock_class]):
        await _show_student_page(mock_message, 1, page=1, edit=False)
        mock_message.answer.assert_called_once()
        assert "Ученики класса 5А" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_back_to_classes(mock_callback):
    """Возврат к списку классов."""
    mock_callback.data = "admin:back_classes"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin._show_classes_for_students', new_callable=AsyncMock) as mock_show:
        await back_to_classes(mock_callback)
        mock_show.assert_awaited_once_with(mock_callback.message, edit=True)
        mock_callback.answer.assert_awaited_once()


# ----- Тесты для добавления/удаления ученика -----

@pytest.mark.asyncio
async def test_add_student_start(mock_callback, mock_state):
    """Начало добавления ученика."""
    mock_callback.data = "admin:addstudent:1"
    with patch('handlers.admin.is_admin', return_value=True):
        await add_student_start(mock_callback, mock_state)
        mock_state.update_data.assert_called_once_with(class_id=1)
        mock_state.set_state.assert_called_once_with(AddStudentStates.waiting_name)
        mock_callback.message.answer.assert_called_once_with("Введите имя и фамилию ученика:")
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_student_name_success(mock_message, mock_state):
    """Успешное добавление ученика."""
    mock_message.text = "Новичков Н.Н."
    mock_state.get_data = AsyncMock(return_value={"class_id": 1})
    with patch('handlers.admin.create_student') as mock_create, \
         patch('handlers.admin._show_student_page', new_callable=AsyncMock) as mock_show:
        await process_student_name(mock_message, mock_state)
        mock_create.assert_called_once_with(name="Новичков Н.Н.", class_id=1)
        mock_state.clear.assert_awaited_once()
        mock_message.answer.assert_called_once_with("✅ Ученик «Новичков Н.Н.» добавлен.")
        mock_show.assert_awaited_once_with(mock_message, 1, page=1)


@pytest.mark.asyncio
async def test_process_student_name_empty(mock_message, mock_state):
    """Пустое имя."""
    mock_message.text = "   "
    await process_student_name(mock_message, mock_state)
    mock_message.answer.assert_called_once_with("Имя не может быть пустым.")
    mock_state.clear.assert_not_called()


@pytest.mark.asyncio
async def test_delete_student_confirm(mock_callback):
    """Подтверждение удаления ученика."""
    mock_callback.data = "admin:delstudent:1:2"
    with patch('handlers.admin.is_admin', return_value=True):
        await delete_student_confirm(mock_callback)
        mock_callback.message.edit_text.assert_called_once()
        assert "Удалить ученика" in mock_callback.message.edit_text.call_args[0][0]
        mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_student_execute(mock_callback):
    """Успешное удаление ученика."""
    mock_callback.data = "admin:delstudentok:1:2"
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.delete_student') as mock_delete, \
         patch('handlers.admin._show_student_page', new_callable=AsyncMock) as mock_show:
        await delete_student_execute(mock_callback)
        mock_delete.assert_called_once_with(1)
        mock_callback.answer.assert_called_once_with("Ученик удалён.")
        mock_show.assert_awaited_once_with(mock_callback.message, 2, page=1, edit=True)


# ----- Тесты для школ -----

@pytest.mark.asyncio
async def test_list_schools_no_schools(mock_message):
    """Нет школ."""
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.get_all_schools', return_value=[]):
        await list_schools(mock_message)
        mock_message.answer.assert_called_once_with("Нет зарегистрированных школ.")


@pytest.mark.asyncio
async def test_list_schools_with_schools(mock_message):
    """Есть школы."""
    schools = [{"id": 1, "name": "Основная школа"}]
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.get_all_schools', return_value=schools), \
         patch('handlers.admin.get_school_id_for_admin', return_value=1):
        await list_schools(mock_message)
        mock_message.answer.assert_called_once()
        assert "Текущая школа: Основная школа" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_switch_school_success(mock_callback):
    """Переключение школы."""
    mock_callback.data = "admin:switch_school:2"
    schools = [{"id": 1, "name": "Школа 1"}, {"id": 2, "name": "Школа 2"}]
    with patch('handlers.admin.is_admin', return_value=True), \
         patch('handlers.admin.set_school_id_for_admin') as mock_set_admin, \
         patch('handlers.admin.set_current_school_id') as mock_set_current, \
         patch('handlers.admin.ensure_admin_teacher') as mock_ensure, \
         patch('handlers.admin.get_all_schools', return_value=schools), \
         patch('handlers.admin.build_menu_keyboard', return_value=Mock()):
        await switch_school(mock_callback)
        mock_set_admin.assert_called_once_with(mock_callback.from_user.id, 2)
        mock_set_current.assert_called_once_with(2)
        mock_ensure.assert_called_once_with(mock_callback.from_user.id, 2)
        mock_callback.message.delete.assert_awaited_once()
        mock_callback.message.answer.assert_any_call("✅ Активная школа: Школа 2 (ID: 2)")
        mock_callback.answer.assert_awaited_once()


# ----- Тесты для restore_admin -----

@pytest.mark.asyncio
async def test_restore_admin_not_authorized(mock_message):
    """Не админ пытается восстановить."""
    mock_message.from_user.id = 999
    await restore_admin(mock_message)
    mock_message.answer.assert_called_once_with("Нет доступа.")

@pytest.mark.asyncio
async def test_restore_admin_success(mock_message):
    """Успешное восстановление."""
    mock_message.from_user.id = ADMIN_TELEGRAM_ID
    mock_teacher = Mock()
    mock_teacher.role = "some_role"
    with patch('database.SessionLocal') as mock_session_class:
        mock_db = Mock()
        mock_query = Mock()
        mock_query.first = Mock(return_value=mock_teacher)
        mock_db.query = Mock(return_value=mock_query)
        mock_session_class.return_value = mock_db
        await restore_admin(mock_message)
        # Проверяем, что коммит был сделан (это подтверждает, что изменение роли произошло)
        mock_db.commit.assert_called_once()
        mock_message.answer.assert_called_once_with("Роль администратора восстановлена. Нажмите /menu.")


@pytest.mark.asyncio
async def test_restore_admin_not_found(mock_message):
    """Админ не найден в базе."""
    mock_message.from_user.id = ADMIN_TELEGRAM_ID
    with patch('database.SessionLocal') as mock_session_class:
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_session_class.return_value = mock_db
        await restore_admin(mock_message)
        mock_message.answer.assert_called_once_with("Вы не найдены в базе.")