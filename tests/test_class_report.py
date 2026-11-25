# tests/test_class_report.py
"""
Отчёт за четверть для классного руководителя.

Главное, что здесь защищается: класс и период берутся с сервера, а не из
callback_data. Классный руководитель не должен иметь возможности выгрузить
чужой класс, подправив данные кнопки.
"""
from contextlib import contextmanager
from datetime import date
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from core.keyboards import BTN_CLASS_REPORT, back_to_menu_btn
from handlers.my_class import class_report_quarters, class_report_send

Q1 = {
    "id": 1,
    "label": "1-я четверть 2025-2026",
    "short_label": "1-я четверть",
    "date_from": date(2025, 9, 1),
    "date_to": date(2025, 10, 31),
}
Q2 = {
    "id": 2,
    "label": "2-я четверть 2025-2026",
    "short_label": "2-я четверть",
    "date_from": date(2025, 11, 1),
    "date_to": date(2025, 12, 31),
}

TEACHER_ID = 12345
TEACHER_CLASS_ID = 5
SCHOOL_ID = 1


@pytest.fixture
def message():
    msg = AsyncMock(spec=Message)
    msg.from_user = Mock(spec=User)
    msg.from_user.id = TEACHER_ID
    msg.text = BTN_CLASS_REPORT
    msg.chat = Mock(spec=Chat)
    msg.chat.id = 67890
    msg.bot = AsyncMock()
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
def callback():
    cb = AsyncMock(spec=CallbackQuery)
    cb.from_user = Mock(spec=User)
    cb.from_user.id = TEACHER_ID
    cb.message = AsyncMock(spec=Message)
    cb.message.edit_text = AsyncMock()
    cb.message.answer_document = AsyncMock()
    cb.answer = AsyncMock()
    return cb


@pytest.fixture
def teacher():
    t = Mock()
    t.id = 1
    t.telegram_id = TEACHER_ID
    t.school_id = SCHOOL_ID
    t.class_id = TEACHER_CLASS_ID
    t.class_name = "7А"
    t.role = "class_teacher"
    return t


@contextmanager
def common_patches(quarters, teacher_obj, admin=False):
    """Патчит зависимости раздела «Мой класс» на время теста."""
    with patch("handlers.my_class.reset_screen", new=AsyncMock()), \
         patch("handlers.my_class.set_screen", new=AsyncMock()), \
         patch("handlers.my_class.check_access", return_value=True), \
         patch("handlers.my_class.is_admin", return_value=admin), \
         patch("handlers.my_class.get_teacher_by_telegram_id", return_value=teacher_obj), \
         patch("handlers.my_class.get_available_quarters", return_value=quarters):
        yield


@pytest.mark.asyncio
async def test_class_teacher_sees_only_started_quarters(message, teacher):
    """В клавиатуре ровно те четверти, что вернул get_available_quarters."""
    with common_patches([Q1, Q2], teacher):
        await class_report_quarters(message, AsyncMock())

    rows = message.answer.call_args.kwargs["reply_markup"].inline_keyboard
    assert len(rows) == 3  # 2 четверти + «Назад»

    assert rows[0][0].text == "1-я четверть"
    assert rows[0][0].callback_data == "cr:q:2025-09-01:2025-10-31"
    assert rows[1][0].text == "2-я четверть"
    assert rows[2][0].text == back_to_menu_btn().text


@pytest.mark.asyncio
async def test_no_quarters_yet(message, teacher):
    """Учебный год ещё не начался — отчёта нет."""
    with common_patches([], teacher):
        await class_report_quarters(message, AsyncMock())

    assert message.answer.call_count == 1
    assert "ещё не начался" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_report_uses_teachers_own_class(callback, teacher):
    """Выгружается класс учителя, а не тот, что мог бы прийти из кнопки."""
    callback.data = "cr:q:2025-09-01:2025-10-31"

    with common_patches([Q1], teacher), \
         patch("handlers.my_class.get_absences_export_data",
               return_value={"7А": [{"name": "Иванов И.И.", "total": 1}]}) as export, \
         patch("handlers.my_class.generate_absences_excel", return_value=b"xlsx") as excel:
        await class_report_send(callback)

    export.assert_called_once_with(SCHOOL_ID, TEACHER_CLASS_ID, Q1["date_from"], Q1["date_to"])
    excel.assert_called_once()
    callback.message.answer_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_period_cannot_be_widened_via_callback(callback, teacher):
    """Подменённый date_to в callback_data игнорируется — период берётся с сервера."""
    callback.data = "cr:q:2025-09-01:2099-01-01"

    with common_patches([Q1], teacher), \
         patch("handlers.my_class.get_absences_export_data",
               return_value={"7А": [{"name": "Иванов И.И.", "total": 1}]}) as export, \
         patch("handlers.my_class.generate_absences_excel", return_value=b"xlsx"):
        await class_report_send(callback)

    _, _, used_from, used_to = export.call_args[0]
    assert (used_from, used_to) == (Q1["date_from"], Q1["date_to"])


@pytest.mark.asyncio
async def test_started_quarter_without_data_reports_empty(callback, teacher):
    """Четверть началась, но перекличек не было — честное сообщение."""
    callback.data = "cr:q:2025-09-01:2025-10-31"

    with common_patches([Q1], teacher), \
         patch("handlers.my_class.get_absences_export_data", return_value={}), \
         patch("handlers.my_class.generate_absences_excel") as excel:
        await class_report_send(callback)

    excel.assert_not_called()
    callback.message.answer_document.assert_not_awaited()
    assert "Нет данных" in callback.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_teacher_without_class_gets_message(message):
    """Учитель без закреплённого класса не получает отчёт."""
    with common_patches([Q1], None):
        await class_report_quarters(message, AsyncMock())

    assert "не указан класс" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_admin_is_redirected_to_export(message, teacher):
    """Администратору отчёт классрука не положен — отправляем в экспорт пропусков."""
    with common_patches([Q1], teacher, admin=True):
        await class_report_quarters(message, AsyncMock())

    text = message.answer.call_args[0][0]
    assert "Экспорт пропусков" in text
    assert message.answer.call_args.kwargs.get("reply_markup") is None


# ── Проверки на уровне меню и данных ──────────────────────────────────────

def test_class_teacher_menu_has_report_button(teacher):
    """Кнопка «Отчёт за четверть» действительно появляется в меню классрука."""
    from core.keyboards import build_menu_keyboard

    with patch("core.keyboards.is_admin", return_value=False), \
         patch("core.keyboards.get_teacher_by_telegram_id", return_value=teacher):
        keyboard = build_menu_keyboard(TEACHER_ID)

    texts = [button.text for row in keyboard.keyboard for button in row]
    assert BTN_CLASS_REPORT in texts


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    """Школа с двумя классами: 7А (наш) и 7Б (чужой), у всех есть пропуски."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import repositories
    from database import (
        AttendanceRecord, AttendanceSession, Base, Class, School, Student,
    )

    engine = create_engine(
        f"sqlite:///{tmp_path / 'class_report.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(repositories, "SessionLocal", factory)

    db = factory()
    school = School(name="Тестовая школа")
    db.add(school)
    db.commit()

    own = Class(name="7А", grade=7, letter="А", school_id=school.id)
    other = Class(name="7Б", grade=7, letter="Б", school_id=school.id)
    db.add_all([own, other])
    db.commit()

    for cls in (own, other):
        students = [
            Student(name=f"{cls.name} ученик {i + 1}", class_id=cls.id, school_id=school.id)
            for i in range(2)
        ]
        db.add_all(students)
        db.commit()

        # одна сессия на класс в день — иначе упираемся в uq_class_session_per_day
        session = AttendanceSession(
            class_id=cls.id, school_id=school.id, session_date=date.today(), status="completed"
        )
        db.add(session)
        db.commit()

        for student in students:
            db.add(AttendanceRecord(
                session_id=session.id, student_id=student.id,
                is_present=False, reason="🤒 По болезни",
            ))
    db.commit()

    ids = {"school_id": school.id, "own_class_id": own.id, "other_class_id": other.id}
    db.close()
    yield ids
    engine.dispose()


def test_export_contains_only_requested_class(seeded_db):
    """В отчёт попадает только свой класс, чужой не подмешивается."""
    import repositories

    data = repositories.get_absences_export_data(
        seeded_db["school_id"], seeded_db["own_class_id"]
    )
    assert list(data.keys()) == ["7А"]
    assert len(data["7А"]) == 2
    assert all(row["total"] == 1 for row in data["7А"])


def test_export_without_class_filter_returns_all_classes(seeded_db):
    """Без фильтра по классу (директор/секретарь) отчёт по-прежнему общий."""
    import repositories

    data = repositories.get_absences_export_data(seeded_db["school_id"])
    assert sorted(data.keys()) == ["7А", "7Б"]
