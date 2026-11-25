# tests/test_absence_reasons.py
"""
Регрессия на состав причин отсутствия.

Тест намеренно не использует фикстуры из conftest.py: он поднимает свой
SQLite-движок и проверяет связку «constants -> repositories -> Excel» целиком.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import repositories
from core.constants import (
    ABSENCE_REASONS,
    DEFAULT_ABSENCE_REASON,
    REASON_ORDER,
    REASON_RECUPERATION,
    REASON_SICK,
    REASON_STATEMENT,
    REASON_UNEXCUSED,
)
from database import (
    AttendanceRecord,
    AttendanceSession,
    Base,
    Class,
    School,
    Student,
)
from helpers.excel_export import generate_absences_excel


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'reasons.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield factory
    engine.dispose()


def test_all_reasons_are_unique_and_named():
    """Каждая причина — отдельная строка, и у каждой есть именованная константа."""
    assert len(ABSENCE_REASONS) == len(set(ABSENCE_REASONS))
    assert ABSENCE_REASONS == [
        REASON_SICK,
        REASON_STATEMENT,
        REASON_ORDER,
        REASON_RECUPERATION,
        REASON_UNEXCUSED,
    ]


def test_unexcused_reason_is_last_and_default():
    """«Без уважительной» — последняя кнопка и причина по умолчанию."""
    assert ABSENCE_REASONS[-1] == REASON_UNEXCUSED
    assert DEFAULT_ABSENCE_REASON == REASON_UNEXCUSED


def test_export_has_bucket_for_every_reason(session_factory, monkeypatch):
    """Каждая причина попадает в свою колонку, сумма колонок равна «Всего»."""
    monkeypatch.setattr(repositories, "SessionLocal", session_factory)

    db = session_factory()
    school = School(name="Тестовая школа")
    db.add(school)
    db.commit()
    school_id = school.id

    cls = Class(name="7А", grade=7, letter="А", school_id=school_id)
    db.add(cls)
    db.commit()

    # по одному ученику на каждую причину + один без причины (None)
    names = [f"Ученик {i + 1}" for i in range(len(ABSENCE_REASONS) + 1)]
    students = [
        Student(name=name, class_id=cls.id, school_id=school_id) for name in names
    ]
    db.add_all(students)
    db.commit()
    student_ids = [s.id for s in students]

    session = AttendanceSession(
        class_id=cls.id, school_id=school_id, session_date=date.today(), status="completed"
    )
    db.add(session)
    db.commit()

    reasons = list(ABSENCE_REASONS) + [None]
    for student_id, reason in zip(student_ids, reasons):
        db.add(
            AttendanceRecord(
                session_id=session.id,
                student_id=student_id,
                is_present=False,
                reason=reason,
            )
        )
    db.commit()
    db.close()

    data = repositories.get_absences_export_data(school_id)
    rows = data["7А"]

    totals = {
        key: sum(row[key] for row in rows)
        for key in ("total", "sick", "statement", "order", "recuperation", "unexcused")
    }
    assert totals == {
        "total": 6,  # 5 причин + одна запись без причины (None)
        "sick": 1,
        "statement": 1,
        "order": 1,
        "recuperation": 1,
        # причина «По приказу» не должна попасть сюда
        "unexcused": 2,  # явная «без уважительной» + reason=None
    }

    # Excel: колонка существует и получает то же значение
    from io import BytesIO

    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(generate_absences_excel(data, title_info="Тест")))
    sheet = workbook.active
    headers = [cell.value for cell in sheet[3]]

    assert "По приказу" in headers
    order_column = headers.index("По приказу") + 1
    assert sum(
        sheet.cell(row=row, column=order_column).value or 0
        for row in range(4, 4 + len(rows))
    ) == 1
