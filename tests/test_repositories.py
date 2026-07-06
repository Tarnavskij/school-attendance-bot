import pytest
from datetime import date
from database import Class, Student, Teacher, AttendanceSession, AttendanceRecord, MealRequest, MealRequestItem
from repositories import (
    get_teacher_by_telegram_id,
    create_teacher,
    get_all_classes,
    get_available_classes,
    create_student,
    get_students_by_class,
    create_session,
    toggle_student_presence,
    get_session_records,
    finish_session,
    get_session_result,
    get_absent_students_today,
    get_or_create_meal_request,
    save_meal_request,
    update_student_meal_type,
    SessionAlreadyExists,
    MealItemDTO,
)

# ----- Фикстуры для создания тестовых данных -----

@pytest.fixture
def school_id(test_db):
    from database import School
    return test_db.query(School).first().id

@pytest.fixture
def class_5a(test_db, school_id):
    cls = Class(name="5A", grade=5, letter="A", school_id=school_id)
    test_db.add(cls)
    test_db.commit()
    return cls

@pytest.fixture
def class_5b(test_db, school_id):
    cls = Class(name="5B", grade=5, letter="B", school_id=school_id)
    test_db.add(cls)
    test_db.commit()
    return cls

@pytest.fixture
def teacher(test_db, school_id, class_5a):
    t = Teacher(
        telegram_id=123456789,
        name="Иван Иванов",
        role="subject_teacher",
        class_id=class_5a.id,
        school_id=school_id,
        is_active=True
    )
    test_db.add(t)
    test_db.commit()
    return t

@pytest.fixture
def students(test_db, class_5a):
    students = [
        Student(name="Петров П.П.", class_id=class_5a.id, school_id=class_5a.school_id),
        Student(name="Сидорова А.С.", class_id=class_5a.id, school_id=class_5a.school_id),
        Student(name="Козлов К.К.", class_id=class_5a.id, school_id=class_5a.school_id),
    ]
    test_db.add_all(students)
    test_db.commit()
    return students

# ----- Тесты -----

def test_get_teacher_by_telegram_id(test_db, teacher):
    result = get_teacher_by_telegram_id(123456789)
    assert result is not None
    assert result.name == "Иван Иванов"
    assert result.role == "subject_teacher"
    assert result.class_id == teacher.class_id

def test_create_teacher(test_db, school_id):
    new_teacher = create_teacher(987654321, "Мария Петрова", role="class_teacher")
    assert new_teacher.id is not None
    assert new_teacher.telegram_id == 987654321
    assert new_teacher.role == "class_teacher"

def test_get_all_classes(test_db, school_id, class_5a, class_5b):
    classes = get_all_classes()
    assert len(classes) == 2
    names = {c.name for c in classes}
    assert "5A" in names
    assert "5B" in names

def test_get_available_classes(test_db, school_id, class_5a, class_5b):
    # Создаём сессию для class_5a
    session = AttendanceSession(
        class_id=class_5a.id,
        session_date=date.today(),
        school_id=school_id,
        status="completed"
    )
    test_db.add(session)
    test_db.commit()

    available = get_available_classes(date.today())
    assert len(available) == 1
    assert available[0].id == class_5b.id

def test_create_student(test_db, class_5a):
    student = create_student("Новичков Н.Н.", class_5a.id)
    assert student.id is not None
    assert student.name == "Новичков Н.Н."
    assert student.class_id == class_5a.id

def test_get_students_by_class(test_db, class_5a, students):
    result = get_students_by_class(class_5a.id)
    assert len(result) == 3
    names = {s.name for s in result}
    assert "Петров П.П." in names
    assert "Сидорова А.С." in names
    assert "Козлов К.К." in names

def test_create_session_success(test_db, teacher, class_5a):
    created = create_session(teacher.id, class_5a.id)
    assert created.id is not None

    sess = test_db.query(AttendanceSession).filter(AttendanceSession.id == created.id).first()
    assert sess is not None
    assert sess.class_id == class_5a.id
    assert sess.teacher_id == teacher.id

def test_create_session_already_exists(test_db, teacher, class_5a):
    # Сначала создаём сессию
    sess = AttendanceSession(
        class_id=class_5a.id,
        session_date=date.today(),
        teacher_id=teacher.id,
        school_id=class_5a.school_id,
        status="active"
    )
    test_db.add(sess)
    test_db.commit()

    with pytest.raises(SessionAlreadyExists):
        create_session(teacher.id, class_5a.id)

def test_toggle_student_presence(test_db, teacher, class_5a, students):
    created = create_session(teacher.id, class_5a.id)
    # Добавляем записи
    for s in students:
        test_db.add(AttendanceRecord(
            session_id=created.id,
            student_id=s.id,
            is_present=True
        ))
    test_db.commit()

    # Переключаем студента 1 на отсутствие
    result = toggle_student_presence(created.id, students[0].id)
    assert result is False  # is_present стал False

    # Проверяем, что запись обновилась
    rec = test_db.query(AttendanceRecord).filter(
        AttendanceRecord.session_id == created.id,
        AttendanceRecord.student_id == students[0].id
    ).first()
    assert rec.is_present is False

    # Переключаем обратно
    result2 = toggle_student_presence(created.id, students[0].id)
    assert result2 is True

    # Обновляем объект из БД
    test_db.expire_all()
    rec = test_db.query(AttendanceRecord).filter(
        AttendanceRecord.session_id == created.id,
        AttendanceRecord.student_id == students[0].id
    ).first()
    assert rec.is_present is True

def test_get_session_records(test_db, teacher, class_5a, students):
    created = create_session(teacher.id, class_5a.id)
    for s in students:
        test_db.add(AttendanceRecord(
            session_id=created.id,
            student_id=s.id,
            is_present=True
        ))
    test_db.commit()

    records = get_session_records(created.id)
    assert len(records) == 3
    for rec in records:
        assert rec.is_present is True
        assert rec.reason is None

def test_finish_session(test_db, teacher, class_5a):
    created = create_session(teacher.id, class_5a.id)
    finish_session(created.id, auto=False)

    sess = test_db.query(AttendanceSession).filter(AttendanceSession.id == created.id).first()
    assert sess.status == "completed"
    assert sess.end_time is not None

def test_get_session_result(test_db, teacher, class_5a, students):
    created = create_session(teacher.id, class_5a.id)
    # Добавляем записи: все присутствуют, кроме одного
    for i, s in enumerate(students):
        is_present = i != 1  # второй студент отсутствует
        test_db.add(AttendanceRecord(
            session_id=created.id,
            student_id=s.id,
            is_present=is_present,
            reason="Болеет" if not is_present else None
        ))
    test_db.commit()
    finish_session(created.id, auto=False)

    result = get_session_result(created.id)
    assert result is not None
    assert result.class_name == "5A"
    assert len(result.absent) == 1
    assert result.absent[0][0] == students[1].name
    assert result.absent[0][1] == "Болеет"

def test_get_absent_students_today(test_db, teacher, class_5a, students):
    created = create_session(teacher.id, class_5a.id)
    for s in students:
        test_db.add(AttendanceRecord(
            session_id=created.id,
            student_id=s.id,
            is_present=(s.id != students[2].id),  # третий отсутствует
            reason="Без уважительной причины" if s.id == students[2].id else None
        ))
    test_db.commit()
    finish_session(created.id, auto=False)

    absent = get_absent_students_today(class_5a.id, date.today())
    assert len(absent) == 1
    assert students[2].id in absent
    assert absent[students[2].id]["name"] == students[2].name
    assert absent[students[2].id]["reason"] == "Без уважительной причины"

def test_get_or_create_meal_request_new(test_db, class_5a, students):
    result = get_or_create_meal_request(class_5a.id)
    assert result.class_id == class_5a.id
    assert result.class_name == "5A"
    assert len(result.items) == 3
    for item in result.items:
        assert item.is_eating is True
        assert item.meal_type in ("paid", "free")

def test_save_meal_request(test_db, class_5a, students, teacher):
    items = [
        MealItemDTO(
            student_id=s.id,
            name=s.name,
            meal_type="paid",
            is_eating=(s.id != students[0].id)
        )
        for s in students
    ]

    req = save_meal_request(class_5a.id, teacher.id, items)
    # Получаем созданную заявку из БД
    saved_req = test_db.query(MealRequest).filter(
        MealRequest.class_id == class_5a.id,
        MealRequest.request_date == date.today()
    ).first()
    assert saved_req is not None
    assert saved_req.class_id == class_5a.id

    saved_items = test_db.query(MealRequestItem).filter(
        MealRequestItem.request_id == saved_req.id
    ).all()
    assert len(saved_items) == 3
    for item in saved_items:
        if item.student_id == students[0].id:
            assert item.is_eating is False
        else:
            assert item.is_eating is True

def test_update_student_meal_type(test_db, students):
    student = students[0]
    assert student.meal_type == "paid"

    update_student_meal_type(student.id, "free")
    test_db.refresh(student)
    assert student.meal_type == "free"

    update_student_meal_type(student.id, "paid")
    test_db.refresh(student)
    assert student.meal_type == "paid"