# repositories.py
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from database import SessionLocal, Teacher, Class, Student, AttendanceSession, AttendanceRecord, RegistrationRequest


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
    class_id: int | None
    class_name: str | None


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
    end_time: datetime | None
    absent: list[tuple[str, str | None]]


@dataclass
class CreatedSession:
    id: int


class SessionAlreadyExists(Exception):
    """Поднимается, когда на класс за сегодня уже есть сессия (в т.ч. гонка двух учителей)."""
    pass


def get_teacher_by_telegram_id(telegram_id: int) -> TeacherDTO | None:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.telegram_id == telegram_id).first()
        if not t:
            return None
        return TeacherDTO(id=t.id, telegram_id=t.telegram_id, name=t.name,
                          role=t.role, class_id=t.class_id,
                          class_name=t.class_.name if t.class_ else None)


def get_all_teachers() -> list[TeacherDTO]:
    with get_db() as db:
        return [TeacherDTO(id=t.id, telegram_id=t.telegram_id, name=t.name,
                           role=t.role, class_id=t.class_id,
                           class_name=t.class_.name if t.class_ else None)
                for t in db.query(Teacher).all()]


def create_teacher(telegram_id: int, name: str, role: str = "subject_teacher", class_id: int | None = None) -> TeacherDTO:
    with get_db() as db:
        t = Teacher(telegram_id=telegram_id, name=name, role=role, class_id=class_id)
        db.add(t)
        db.flush()
        return TeacherDTO(id=t.id, telegram_id=t.telegram_id, name=t.name,
                          role=t.role, class_id=t.class_id, class_name=None)


def get_teacher_card(teacher_id: int) -> TeacherDTO | None:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if not t:
            return None
        return TeacherDTO(id=t.id, telegram_id=t.telegram_id, name=t.name,
                          role=t.role, class_id=t.class_id,
                          class_name=t.class_.name if t.class_ else None)


def update_teacher_role(teacher_id: int, new_role: str) -> bool:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if not t:
            return False
        t.role = new_role
        return True


def update_teacher_class(teacher_id: int, class_id: int | None) -> bool:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if not t:
            return False
        t.class_id = class_id
        return True


def delete_teacher(teacher_id: int) -> bool:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if not t:
            return False
        db.delete(t)
        return True


def get_all_classes() -> list[ClassDTO]:
    with get_db() as db:
        return [ClassDTO(id=c.id, name=c.name) for c in db.query(Class).all()]


def get_available_classes(today_date: date) -> list[ClassDTO]:
    """
    Класс доступен для выбора, если по нему СЕГОДНЯ ещё нет ни одной сессии
    (в любом статусе — active, completed или auto_completed).

    Раньше здесь проверялся только status == "active", что позволяло провести
    повторную перекличку в уже отмеченном классе. Теперь — максимум одна
    сессия на класс в день, точка.
    """
    with get_db() as db:
        taken_ids = (db.query(AttendanceSession.class_id)
                    .filter(AttendanceSession.session_date == today_date))
        return [ClassDTO(id=c.id, name=c.name)
                for c in db.query(Class).filter(~Class.id.in_(taken_ids)).all()]


def get_students_by_class(class_id: int) -> list[StudentDTO]:
    with get_db() as db:
        return [StudentDTO(id=s.id, name=s.name, class_id=s.class_id)
                for s in db.query(Student).filter(Student.class_id == class_id).order_by(Student.name).all()]


def create_student(name: str, class_id: int) -> StudentDTO:
    with get_db() as db:
        s = Student(name=name, class_id=class_id)
        db.add(s)
        db.flush()
        return StudentDTO(id=s.id, name=s.name, class_id=s.class_id)


def delete_student(student_id: int) -> bool:
    with get_db() as db:
        s = db.query(Student).filter(Student.id == student_id).first()
        if not s:
            return False
        db.delete(s)
        return True


def create_session(teacher_id: int, class_id: int) -> CreatedSession:
    """
    Создаёт сессию переклички на сегодня.

    Защита от гонки: уникальный констрейнт (class_id, session_date) в БД
    гарантирует, что даже если два учителя почти одновременно прошли проверку
    get_available_classes, только один INSERT пройдёт — второй упадёт
    с IntegrityError, которую мы превращаем в понятное исключение SessionAlreadyExists.
    """
    today = date.today()
    with get_db() as db:
        s = AttendanceSession(teacher_id=teacher_id, class_id=class_id, session_date=today)
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
            joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
        ).filter(AttendanceSession.id == session_id).first()
        if not s:
            return None
        return SessionDTO(id=s.id,
                          teacher_name=s.teacher.name if s.teacher else "?",
                          class_name=s.class_.name if s.class_ else "?",
                          end_time=s.end_time,
                          absent=[(r.student.name, r.reason) for r in s.records if not r.is_present])


def get_active_sessions(today_date: date) -> list[CreatedSession]:
    with get_db() as db:
        return [CreatedSession(id=s.id)
                for s in db.query(AttendanceSession).filter(
                    AttendanceSession.status == "active",
                    AttendanceSession.session_date == today_date).all()]


def get_sessions_for_report(target_date: date) -> list[SessionDTO]:
    with get_db() as db:
        sessions = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.teacher),
            joinedload(AttendanceSession.class_),
            joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
        ).filter(AttendanceSession.session_date == target_date,
                 AttendanceSession.status.in_(["completed", "auto_completed"])).all()
        return [SessionDTO(id=s.id,
                           teacher_name=s.teacher.name if s.teacher else "?",
                           class_name=s.class_.name if s.class_ else "?",
                           end_time=s.end_time,
                           absent=[(r.student.name, r.reason) for r in s.records if not r.is_present])
                for s in sessions]


def set_absence_reason(student_id: int, class_id: int, target_date: date, reason: str) -> None:
    """
    Устанавливает причину отсутствия ученика за день.

    Так как на класс — максимум одна сессия в день, здесь достаточно найти
    эту единственную сессию (если она есть) и обновить запись в ней.
    Раньше тут был цикл по нескольким сессиям дня — это больше не нужно.
    """
    with get_db() as db:
        sess = db.query(AttendanceSession).filter(
            AttendanceSession.class_id == class_id,
            AttendanceSession.session_date == target_date,
            AttendanceSession.status.in_(["completed", "auto_completed"]),
        ).first()
        if not sess:
            return
        db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == sess.id,
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.is_present.is_(False),
        ).update({"reason": reason})


def get_absent_students_today(class_id: int, today_date: date) -> dict[int, dict]:
    """
    Возвращает отсутствующих сегодня в классе.

    Так как на класс — максимум одна сессия в день, здесь больше не нужно
    объединять причины из нескольких сессий — берём записи единственной сессии.
    """
    with get_db() as db:
        sess = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
        ).filter(AttendanceSession.class_id == class_id,
                 AttendanceSession.status.in_(["completed", "auto_completed"]),
                 AttendanceSession.session_date == today_date).first()

        if not sess:
            return {}

        result: dict[int, dict] = {}
        for rec in sess.records:
            if not rec.is_present:
                result[rec.student_id] = {"name": rec.student.name, "reason": rec.reason}
        return result


# ===== Функции для работы с заявками =====

def get_pending_requests() -> list[dict]:
    """Возвращает список активных заявок на регистрацию с человекочитаемыми метками."""
    from core.roles import ROLE_LABELS
    with get_db() as db:
        reqs = db.query(RegistrationRequest).filter(RegistrationRequest.status == "pending").all()
        return [{
            'id': r.id,
            'telegram_id': r.telegram_id,
            'name': r.name,
            'role': r.role,
            'role_label': ROLE_LABELS.get(r.role, r.role),
            'class_name': r.class_name,
        } for r in reqs]


def approve_request(req_id: int) -> bool:
    """Одобряет заявку и создаёт учителя. Возвращает True при успехе."""
    with get_db() as db:
        req = db.query(RegistrationRequest).filter(
            RegistrationRequest.id == req_id,
            RegistrationRequest.status == "pending"
        ).first()
        if not req:
            return False
        class_id = None
        if req.class_name:
            c = db.query(Class).filter(Class.name == req.class_name).first()
            if c:
                class_id = c.id
        teacher = Teacher(
            telegram_id=req.telegram_id,
            name=req.name,
            role=req.role,
            class_id=class_id,
        )
        db.add(teacher)
        req.status = "approved"
        return True


def reject_request(req_id: int) -> None:
    """Отклоняет заявку (ставит статус rejected)."""
    with get_db() as db:
        req = db.query(RegistrationRequest).filter(
            RegistrationRequest.id == req_id,
            RegistrationRequest.status == "pending"
        ).first()
        if req:
            req.status = "rejected"


# ===== Функции для директора и секретаря =====

def is_class_done_today(class_id: int, today_date: date) -> bool:
    """Проверяет, завершена ли перекличка в классе сегодня (есть сессия completed/auto_completed)."""
    with get_db() as db:
        exists = db.query(AttendanceSession).filter(
            AttendanceSession.class_id == class_id,
            AttendanceSession.session_date == today_date,
            AttendanceSession.status.in_(["completed", "auto_completed"]),
        ).first()
        return exists is not None


def is_school_done_today(today_date: date) -> bool:
    """
    Перекличка по школе готова, если не осталось классов с ЕЩЁ ИДУЩЕЙ (active)
    перекличкой. Класс, который сегодня вообще не отмечался (например, уехал
    на экскурсию) — это нормальный сценарий и не блокирует готовность.

    Один запрос вместо N+1.
    """
    with get_db() as db:
        classes_count = db.query(Class).count()
        if classes_count == 0:
            return False
        active_exists = db.query(AttendanceSession).filter(
            AttendanceSession.session_date == today_date,
            AttendanceSession.status == "active",
        ).first()
        return active_exists is None


def get_absence_reason_counts(target_date: date) -> dict[str, int]:
    """
    Считает количество отсутствующих сегодня по каждой причине (по всей школе),
    плюс общий итог. Если причина не указана (None), относит к DEFAULT_ABSENCE_REASON.
    """
    from core.constants import DEFAULT_ABSENCE_REASON
    with get_db() as db:
        sessions = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.records),
        ).filter(
            AttendanceSession.session_date == target_date,
            AttendanceSession.status.in_(["completed", "auto_completed"]),
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