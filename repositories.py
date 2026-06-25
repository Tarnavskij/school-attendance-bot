# repositories.py
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from database import SessionLocal, Teacher, Class, Student, AttendanceSession, AttendanceRecord, RegistrationRequest, School
from core.school_context import get_current_school_id

@contextmanager
def get_db():
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@dataclass
class TeacherDTO:
    id: int
    telegram_id: int
    name: str
    role: str
    is_active: bool
    class_id: int | None
    class_name: str | None
    school_name: str | None


@dataclass
class ClassDTO:
    id: int
    name: str


@dataclass
class StudentDTO:
    id: int
    name: str
    class_id: int


@dataclass
class RecordDTO:
    student_id: int
    is_present: bool
    reason: str | None


@dataclass
class SessionDTO:
    id: int
    teacher_name: str
    class_name: str
    class_id: int
    end_time: datetime | None
    absent: list[tuple[str, str | None]]
    school_name: str | None


@dataclass
class CreatedSession:
    id: int


class SessionAlreadyExists(Exception):
    pass


def get_teacher_by_telegram_id(telegram_id: int) -> TeacherDTO | None:
    """Возвращает активного учителя в текущей школе (для админа) или в любой школе (для обычных пользователей)."""
    with get_db() as db:
        # Если запрос от администратора – ищем в текущей школе
        if get_current_school_id() == 1:   # админский контекст всегда 1, но для безопасности проверяем роль
            from core.roles import is_admin
            if is_admin(telegram_id):
                t = db.query(Teacher).options(joinedload(Teacher.school)).filter(
                    Teacher.telegram_id == telegram_id,
                    Teacher.school_id == get_current_school_id(),
                    Teacher.is_active == True
                ).first()
                if not t:
                    return None
                return TeacherDTO(
                    id=t.id, telegram_id=t.telegram_id, name=t.name,
                    role=t.role, is_active=t.is_active,
                    class_id=t.class_id,
                    class_name=t.class_.name if t.class_ else None,
                    school_name=t.school.name if t.school else None
                )
        # Для обычного пользователя ищем активного учителя в любой школе
        t = db.query(Teacher).options(joinedload(Teacher.school)).filter(
            Teacher.telegram_id == telegram_id,
            Teacher.is_active == True
        ).first()
        if not t:
            return None
        return TeacherDTO(
            id=t.id, telegram_id=t.telegram_id, name=t.name,
            role=t.role, is_active=t.is_active,
            class_id=t.class_id,
            class_name=t.class_.name if t.class_ else None,
            school_name=t.school.name if t.school else None
        )


def get_all_teachers() -> list[TeacherDTO]:
    with get_db() as db:
        return [
            TeacherDTO(
                id=t.id, telegram_id=t.telegram_id, name=t.name,
                role=t.role, is_active=t.is_active,
                class_id=t.class_id,
                class_name=t.class_.name if t.class_ else None,
                school_name=t.school.name if t.school else None
            )
            for t in db.query(Teacher).options(joinedload(Teacher.school)).filter(
                Teacher.school_id == get_current_school_id()
            ).all()
        ]


def create_teacher(telegram_id: int, name: str, role: str = "subject_teacher", class_id: int | None = None) -> TeacherDTO:
    with get_db() as db:
        t = Teacher(telegram_id=telegram_id, name=name, role=role, class_id=class_id,
                    school_id=get_current_school_id(), is_active=True)
        db.add(t)
        db.flush()
        return TeacherDTO(
            id=t.id, telegram_id=t.telegram_id, name=t.name,
            role=t.role, is_active=t.is_active,
            class_id=t.class_id, class_name=None,
            school_name=None
        )


def get_teacher_card(teacher_id: int) -> TeacherDTO | None:
    with get_db() as db:
        t = db.query(Teacher).options(joinedload(Teacher.school)).filter(
            Teacher.id == teacher_id,
            Teacher.school_id == get_current_school_id()
        ).first()
        if not t:
            return None
        return TeacherDTO(
            id=t.id, telegram_id=t.telegram_id, name=t.name,
            role=t.role, is_active=t.is_active,
            class_id=t.class_id,
            class_name=t.class_.name if t.class_ else None,
            school_name=t.school.name if t.school else None
        )


def update_teacher_role(teacher_id: int, new_role: str) -> bool:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id,
                                     Teacher.school_id == get_current_school_id()).first()
        if not t:
            return False
        t.role = new_role
        return True


def update_teacher_class(teacher_id: int, class_id: int | None) -> bool:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id,
                                     Teacher.school_id == get_current_school_id()).first()
        if not t:
            return False
        t.class_id = class_id
        return True


def delete_teacher(teacher_id: int) -> bool:
    """Физическое удаление учителя и всех его заявок в этой школе."""
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id,
                                     Teacher.school_id == get_current_school_id()).first()
        if not t:
            return False
        # Удаляем все заявки этого пользователя в данной школе
        db.query(RegistrationRequest).filter(
            RegistrationRequest.telegram_id == t.telegram_id,
            RegistrationRequest.school_id == get_current_school_id()
        ).delete()
        db.delete(t)
        return True


def deactivate_teacher(teacher_id: int) -> bool:
    """Мягкое удаление: учитель остаётся в базе, но становится неактивным."""
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id,
                                     Teacher.school_id == get_current_school_id()).first()
        if not t:
            return False
        t.is_active = False
        return True


def activate_teacher(teacher_id: int) -> bool:
    """Повторная активация деактивированного учителя."""
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id,
                                     Teacher.school_id == get_current_school_id()).first()
        if not t:
            return False
        t.is_active = True
        return True


def get_all_classes() -> list[ClassDTO]:
    with get_db() as db:
        return [ClassDTO(id=c.id, name=c.name)
                for c in db.query(Class).filter(Class.school_id == get_current_school_id()).all()]


def get_available_classes(today_date: date, is_admin_user: bool = False) -> list[ClassDTO]:
    """Классы, доступные для выбора. Администратору – все, учителям – только незанятые."""
    if is_admin_user:
        with get_db() as db:
            return [ClassDTO(id=c.id, name=c.name)
                    for c in db.query(Class).filter(Class.school_id == get_current_school_id()).all()]
    with get_db() as db:
        taken_ids = (db.query(AttendanceSession.class_id)
                     .filter(AttendanceSession.session_date == today_date,
                             AttendanceSession.school_id == get_current_school_id()))
        return [ClassDTO(id=c.id, name=c.name)
                for c in db.query(Class).filter(Class.school_id == get_current_school_id(),
                                                ~Class.id.in_(taken_ids)).all()]


def get_students_by_class(class_id: int) -> list[StudentDTO]:
    with get_db() as db:
        return [StudentDTO(id=s.id, name=s.name, class_id=s.class_id)
                for s in db.query(Student).filter(Student.class_id == class_id,
                                                  Student.school_id == get_current_school_id())
                .order_by(Student.name).all()]


def create_student(name: str, class_id: int) -> StudentDTO:
    with get_db() as db:
        s = Student(name=name, class_id=class_id, school_id=get_current_school_id())
        db.add(s)
        db.flush()
        return StudentDTO(id=s.id, name=s.name, class_id=s.class_id)


def delete_student(student_id: int) -> bool:
    with get_db() as db:
        s = db.query(Student).filter(Student.id == student_id,
                                     Student.school_id == get_current_school_id()).first()
        if not s:
            return False
        db.delete(s)
        return True


def create_session(teacher_id: int, class_id: int) -> CreatedSession:
    today = date.today()
    with get_db() as db:
        s = AttendanceSession(teacher_id=teacher_id, class_id=class_id, session_date=today,
                              school_id=get_current_school_id())
        db.add(s)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise SessionAlreadyExists(f"Класс {class_id} уже отмечался сегодня.")
        return CreatedSession(id=s.id)


def add_records(session_id: int, student_ids: list[int]) -> None:
    with get_db() as db:
        db.bulk_save_objects([
            AttendanceRecord(session_id=session_id, student_id=sid, is_present=True)
            for sid in student_ids
        ])


def toggle_student_presence(session_id: int, student_id: int) -> bool:
    with get_db() as db:
        rec = db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == session_id,
            AttendanceRecord.student_id == student_id,
        ).first()
        if not rec:
            return True
        rec.is_present = not rec.is_present
        return rec.is_present


def get_session_records(session_id: int) -> list[RecordDTO]:
    with get_db() as db:
        return [RecordDTO(student_id=r.student_id, is_present=r.is_present, reason=r.reason)
                for r in db.query(AttendanceRecord).filter(AttendanceRecord.session_id == session_id).all()]


def finish_session(session_id: int, auto: bool = False) -> None:
    with get_db() as db:
        s = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
        if s:
            s.end_time = datetime.now()
            s.status = "auto_completed" if auto else "completed"


def delete_session(session_id: int) -> None:
    with get_db() as db:
        s = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
        if s:
            db.delete(s)


def get_session_result(session_id: int) -> SessionDTO | None:
    with get_db() as db:
        s = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.teacher),
            joinedload(AttendanceSession.class_),
            joinedload(AttendanceSession.school),
            joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
        ).filter(AttendanceSession.id == session_id).first()
        if not s:
            return None
        return SessionDTO(
            id=s.id,
            teacher_name=s.teacher.name if s.teacher else "?",
            class_name=s.class_.name if s.class_ else "?",
            class_id=s.class_id,
            end_time=s.end_time,
            absent=[(r.student.name, r.reason) for r in s.records if not r.is_present],
            school_name=s.school.name if s.school else None
        )


def get_active_sessions(today_date: date) -> list[CreatedSession]:
    with get_db() as db:
        return [CreatedSession(id=s.id)
                for s in db.query(AttendanceSession).filter(
                    AttendanceSession.status == "active",
                    AttendanceSession.session_date == today_date,
                    AttendanceSession.school_id == get_current_school_id()).all()]


def get_sessions_for_report(target_date: date) -> list[SessionDTO]:
    with get_db() as db:
        sessions = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.teacher),
            joinedload(AttendanceSession.class_),
            joinedload(AttendanceSession.school),
            joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
        ).filter(AttendanceSession.session_date == target_date,
                 AttendanceSession.status.in_(["completed", "auto_completed"]),
                 AttendanceSession.school_id == get_current_school_id()).all()
        return [SessionDTO(id=s.id,
                           teacher_name=s.teacher.name if s.teacher else "?",
                           class_name=s.class_.name if s.class_ else "?",
                           class_id=s.class_id,
                           end_time=s.end_time,
                           absent=[(r.student.name, r.reason) for r in s.records if not r.is_present],
                           school_name=s.school.name if s.school else None)
                for s in sessions]


def set_absence_reason(student_id: int, class_id: int, target_date: date, reason: str) -> None:
    with get_db() as db:
        sess = db.query(AttendanceSession).filter(
            AttendanceSession.class_id == class_id,
            AttendanceSession.session_date == target_date,
            AttendanceSession.status.in_(["completed", "auto_completed"]),
            AttendanceSession.school_id == get_current_school_id(),
        ).first()
        if not sess:
            return
        db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == sess.id,
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.is_present.is_(False),
        ).update({"reason": reason})


def get_absent_students_today(class_id: int, today_date: date) -> dict[int, dict]:
    with get_db() as db:
        sess = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
        ).filter(AttendanceSession.class_id == class_id,
                 AttendanceSession.status.in_(["completed", "auto_completed"]),
                 AttendanceSession.session_date == today_date,
                 AttendanceSession.school_id == get_current_school_id()).first()

        if not sess:
            return {}

        result: dict[int, dict] = {}
        for rec in sess.records:
            if not rec.is_present:
                result[rec.student_id] = {"name": rec.student.name, "reason": rec.reason}
        return result


def get_pending_requests() -> list[dict]:
    from core.roles import ROLE_LABELS
    with get_db() as db:
        reqs = db.query(RegistrationRequest).filter(RegistrationRequest.status == "pending",
                                                    RegistrationRequest.school_id == get_current_school_id()).all()
        return [{
            'id': r.id,
            'telegram_id': r.telegram_id,
            'name': r.name,
            'role': r.role,
            'role_label': ROLE_LABELS.get(r.role, r.role),
            'class_name': r.class_name,
        } for r in reqs]


def approve_request(req_id: int) -> bool:
    with get_db() as db:
        req = db.query(RegistrationRequest).filter(
            RegistrationRequest.id == req_id,
            RegistrationRequest.status == "pending",
            RegistrationRequest.school_id == get_current_school_id()
        ).first()
        if not req:
            return False

        # Проверяем, нет ли уже неактивного учителя с таким telegram_id в этой школе
        inactive_teacher = db.query(Teacher).filter(
            Teacher.telegram_id == req.telegram_id,
            Teacher.school_id == get_current_school_id(),
            Teacher.is_active == False
        ).first()

        if inactive_teacher:
            # Реактивируем и обновляем данные
            inactive_teacher.is_active = True
            inactive_teacher.role = req.role
            inactive_teacher.name = req.name
            if req.class_name:
                c = db.query(Class).filter(Class.name == req.class_name,
                                           Class.school_id == get_current_school_id()).first()
                if c:
                    inactive_teacher.class_id = c.id
            req.status = "approved"
            return True

        # Проверяем активного учителя
        active_teacher = db.query(Teacher).filter(
            Teacher.telegram_id == req.telegram_id,
            Teacher.school_id == get_current_school_id(),
            Teacher.is_active == True
        ).first()
        if active_teacher:
            req.status = "rejected"
            return False

        # Создаём нового учителя
        class_id = None
        if req.class_name:
            c = db.query(Class).filter(Class.name == req.class_name,
                                       Class.school_id == get_current_school_id()).first()
            if c:
                class_id = c.id
        teacher = Teacher(
            telegram_id=req.telegram_id,
            name=req.name,
            role=req.role,
            class_id=class_id,
            school_id=get_current_school_id(),
        )
        db.add(teacher)
        req.status = "approved"
        return True


def reject_request(req_id: int) -> None:
    with get_db() as db:
        req = db.query(RegistrationRequest).filter(
            RegistrationRequest.id == req_id,
            RegistrationRequest.status == "pending",
            RegistrationRequest.school_id == get_current_school_id()
        ).first()
        if req:
            req.status = "rejected"


def is_class_done_today(class_id: int, today_date: date) -> bool:
    with get_db() as db:
        exists = db.query(AttendanceSession).filter(
            AttendanceSession.class_id == class_id,
            AttendanceSession.session_date == today_date,
            AttendanceSession.status.in_(["completed", "auto_completed"]),
            AttendanceSession.school_id == get_current_school_id(),
        ).first()
        return exists is not None


def is_school_done_today(today_date: date) -> bool:
    with get_db() as db:
        classes_count = db.query(Class).filter(Class.school_id == get_current_school_id()).count()
        if classes_count == 0:
            return False
        active_exists = db.query(AttendanceSession).filter(
            AttendanceSession.session_date == today_date,
            AttendanceSession.status == "active",
            AttendanceSession.school_id == get_current_school_id(),
        ).first()
        return active_exists is None


def get_absence_reason_counts(target_date: date) -> dict[str, int]:
    from core.constants import DEFAULT_ABSENCE_REASON
    with get_db() as db:
        sessions = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.records),
        ).filter(
            AttendanceSession.session_date == target_date,
            AttendanceSession.status.in_(["completed", "auto_completed"]),
            AttendanceSession.school_id == get_current_school_id(),
        ).all()

        counts: dict[str, int] = {}
        total = 0
        for sess in sessions:
            for rec in sess.records:
                if not rec.is_present:
                    total += 1
                    reason = rec.reason or DEFAULT_ABSENCE_REASON
                    counts[reason] = counts.get(reason, 0) + 1
        counts["__total__"] = total
        return counts


def reset_today_sessions() -> int:
    today = date.today()
    with get_db() as db:
        sessions = db.query(AttendanceSession).filter(
            AttendanceSession.session_date == today,
            AttendanceSession.school_id == get_current_school_id(),
        ).all()
        count = len(sessions)
        for s in sessions:
            db.delete(s)
        return count


def get_teacher_session_today(teacher_id: int, today_date: date) -> SessionDTO | None:
    with get_db() as db:
        s = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.teacher),
            joinedload(AttendanceSession.class_),
            joinedload(AttendanceSession.school),
            joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
        ).filter(
            AttendanceSession.teacher_id == teacher_id,
            AttendanceSession.session_date == today_date,
            AttendanceSession.school_id == get_current_school_id(),
        ).first()
        if not s:
            return None
        return SessionDTO(
            id=s.id,
            teacher_name=s.teacher.name if s.teacher else "?",
            class_name=s.class_.name if s.class_ else "?",
            class_id=s.class_id,
            end_time=s.end_time,
            absent=[(r.student.name, r.reason) for r in s.records if not r.is_present],
            school_name=s.school.name if s.school else None
        )


# ===== Школы (глобальные, без фильтра) =====

def get_all_schools() -> list[dict]:
    """Возвращает список всех школ (id, name)."""
    with get_db() as db:
        schools = db.query(School).all()
        return [{"id": s.id, "name": s.name} for s in schools]


def create_school(name: str) -> dict:
    """Создаёт новую школу и возвращает её id и name."""
    with get_db() as db:
        school = School(name=name)
        db.add(school)
        db.flush()
        return {"id": school.id, "name": school.name}


def get_teachers_paginated(page: int = 1, per_page: int = 5):
    """Возвращает учителей текущей школы с пагинацией и общее количество."""
    with get_db() as db:
        query = db.query(Teacher).options(joinedload(Teacher.school)).filter(
            Teacher.school_id == get_current_school_id()
        )
        total = query.count()
        teachers = query.order_by(Teacher.name).offset((page - 1) * per_page).limit(per_page).all()
        result = [
            TeacherDTO(
                id=t.id, telegram_id=t.telegram_id, name=t.name,
                role=t.role, is_active=t.is_active,
                class_id=t.class_id,
                class_name=t.class_.name if t.class_ else None,
                school_name=t.school.name if t.school else None
            )
            for t in teachers
        ]
        return result, total


def get_students_by_class_paginated(class_id: int, page: int = 1, per_page: int = 8):
    """Возвращает учеников класса с пагинацией и общее количество."""
    with get_db() as db:
        query = db.query(Student).filter(
            Student.class_id == class_id,
            Student.school_id == get_current_school_id()
        )
        total = query.count()
        students = query.order_by(Student.name).offset((page - 1) * per_page).limit(per_page).all()
        result = [StudentDTO(id=s.id, name=s.name, class_id=s.class_id) for s in students]
        return result, total


def get_class_teacher_for_class(class_id: int) -> TeacherDTO | None:
    """Находит классного руководителя для указанного класса в текущей школе."""
    with get_db() as db:
        t = db.query(Teacher).filter(
            Teacher.class_id == class_id,
            Teacher.role == "class_teacher",
            Teacher.school_id == get_current_school_id()
        ).first()
        if not t:
            return None
        return TeacherDTO(
            id=t.id, telegram_id=t.telegram_id, name=t.name,
            role=t.role, is_active=t.is_active,
            class_id=t.class_id,
            class_name=t.class_.name if t.class_ else None,
            school_name=t.school.name if t.school else None
        )