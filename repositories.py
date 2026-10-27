# repositories.py
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from sqlalchemy import extract
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from database import SessionLocal, Teacher, Class, Student, AttendanceSession, AttendanceRecord, RegistrationRequest, \
    School, MealRequest, MealRequestItem

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
    school_id: int
    class_id: int | None
    class_name: str | None
    school_name: str | None


@dataclass
class ClassDTO:
    id: int
    name: str
    school_id: int
    grade: int | None = None
    letter: str | None = None


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
    status: str = "completed"


@dataclass
class CreatedSession:
    id: int


class SessionAlreadyExists(Exception):
    pass


# ===== Учителя =====

def get_default_school_id() -> int:
    with get_db() as db:
        school = db.query(School).first()
        if school:
            return school.id
        new_school = School(name="Основная школа")
        db.add(new_school)
        db.commit()
        return new_school.id

def get_all_active_telegram_ids() -> list[int]:
    """Возвращает ID всех активных учителей для рассылки."""
    with get_db() as db:
        teachers = db.query(Teacher.telegram_id).filter(Teacher.is_active == True).all()
        return [t[0] for t in teachers]

def get_teacher_by_telegram_id(telegram_id: int) -> TeacherDTO | None:
    with get_db() as db:
        t = db.query(Teacher).options(joinedload(Teacher.school)).filter(
            Teacher.telegram_id == telegram_id,
            Teacher.is_active == True
        ).first()
        if not t:
            return None
        return TeacherDTO(
            id=t.id, telegram_id=t.telegram_id, name=t.name,
            role=t.role, is_active=t.is_active,
            school_id=t.school_id,
            class_id=t.class_id,
            class_name=t.class_.name if t.class_ else None,
            school_name=t.school.name if t.school else None
        )


def get_all_teachers(school_id: int) -> list[TeacherDTO]:
    with get_db() as db:
        return [
            TeacherDTO(
                id=t.id, telegram_id=t.telegram_id, name=t.name,
                role=t.role, is_active=t.is_active,
                school_id=t.school_id,
                class_id=t.class_id,
                class_name=t.class_.name if t.class_ else None,
                school_name=t.school.name if t.school else None
            )
            for t in db.query(Teacher).options(joinedload(Teacher.school))
            .filter(Teacher.school_id == school_id).all()
        ]


def create_teacher(telegram_id: int, name: str, school_id: int,
                   role: str = "subject_teacher",
                   class_id: int | None = None) -> TeacherDTO:
    with get_db() as db:
        t = Teacher(telegram_id=telegram_id, name=name, role=role,
                    class_id=class_id, school_id=school_id, is_active=True)
        db.add(t)
        db.flush()
        return TeacherDTO(
            id=t.id, telegram_id=t.telegram_id, name=t.name,
            role=t.role, is_active=t.is_active,
            school_id=t.school_id,
            class_id=t.class_id, class_name=None,
            school_name=None
        )


def get_teacher_card(teacher_id: int, school_id: int) -> TeacherDTO | None:
    with get_db() as db:
        t = db.query(Teacher).options(joinedload(Teacher.school)).filter(
            Teacher.id == teacher_id,
            Teacher.school_id == school_id
        ).first()
        if not t:
            return None
        return TeacherDTO(
            id=t.id, telegram_id=t.telegram_id, name=t.name,
            role=t.role, is_active=t.is_active,
            school_id=t.school_id,
            class_id=t.class_id,
            class_name=t.class_.name if t.class_ else None,
            school_name=t.school.name if t.school else None
        )


def update_teacher_role(teacher_id: int, new_role: str, school_id: int) -> bool:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id,
                                     Teacher.school_id == school_id).first()
        if not t:
            return False
        t.role = new_role
        return True


def update_teacher_class(teacher_id: int, class_id: int | None, school_id: int) -> bool:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id,
                                     Teacher.school_id == school_id).first()
        if not t:
            return False
        t.class_id = class_id
        return True


def delete_teacher(teacher_id: int, school_id: int) -> bool:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id,
                                     Teacher.school_id == school_id).first()
        if not t:
            return False
        db.query(RegistrationRequest).filter(
            RegistrationRequest.telegram_id == t.telegram_id,
            RegistrationRequest.school_id == school_id
        ).delete()
        db.delete(t)
        return True


def deactivate_teacher(teacher_id: int, school_id: int) -> bool:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id,
                                     Teacher.school_id == school_id).first()
        if not t:
            return False
        t.is_active = False
        return True


def activate_teacher(teacher_id: int, school_id: int) -> bool:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id,
                                     Teacher.school_id == school_id).first()
        if not t:
            return False
        t.is_active = True
        return True


# ===== Классы и ученики =====

def get_all_classes(school_id: int) -> list[ClassDTO]:
    with get_db() as db:
        return [ClassDTO(id=c.id, name=c.name, school_id=c.school_id, grade=c.grade, letter=c.letter)
                for c in db.query(Class).filter(Class.school_id == school_id)
                .order_by(Class.grade, Class.letter).all()]


def get_available_classes(today_date: date, school_id: int) -> list[ClassDTO]:
    with get_db() as db:
        taken_ids = (
            db.query(AttendanceSession.class_id)
            .filter(
                AttendanceSession.session_date == today_date,
                AttendanceSession.school_id == school_id,
            )
        )
        return [
            ClassDTO(id=c.id, name=c.name, school_id=c.school_id, grade=c.grade, letter=c.letter)
            for c in db.query(Class)
            .filter(
                Class.school_id == school_id,
                ~Class.id.in_(taken_ids),
            )
            .order_by(Class.grade, Class.letter)
            .all()
        ]


def get_students_by_class(class_id: int, school_id: int) -> list[StudentDTO]:
    with get_db() as db:
        return [StudentDTO(id=s.id, name=s.name, class_id=s.class_id)
                for s in db.query(Student).filter(Student.class_id == class_id,
                                                  Student.school_id == school_id)
                .order_by(Student.name).all()]


def create_student(name: str, class_id: int, school_id: int) -> StudentDTO:
    with get_db() as db:
        s = Student(name=name, class_id=class_id, school_id=school_id)
        db.add(s)
        db.flush()
        return StudentDTO(id=s.id, name=s.name, class_id=s.class_id)


def delete_student(student_id: int, school_id: int) -> bool:
    with get_db() as db:
        s = db.query(Student).filter(Student.id == student_id,
                                     Student.school_id == school_id).first()
        if not s:
            return False
        db.delete(s)
        return True


# ===== Перекличка =====

def create_session(teacher_id: int, class_id: int, school_id: int) -> CreatedSession:
    today = date.today()
    with get_db() as db:
        s = AttendanceSession(teacher_id=teacher_id, class_id=class_id,
                              session_date=today, school_id=school_id)
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
            school_name=s.school.name if s.school else None,
            status=s.status,
        )


def get_active_sessions(today_date: date, school_id: int) -> list[CreatedSession]:
    with get_db() as db:
        return [CreatedSession(id=s.id)
                for s in db.query(AttendanceSession).filter(
                    AttendanceSession.status == "active",
                    AttendanceSession.session_date == today_date,
                    AttendanceSession.school_id == school_id).all()]


def get_sessions_for_report(target_date: date, school_id: int) -> list[SessionDTO]:
    with get_db() as db:
        sessions = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.teacher),
            joinedload(AttendanceSession.class_),
            joinedload(AttendanceSession.school),
            joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
        ).filter(AttendanceSession.session_date == target_date,
                 AttendanceSession.status.in_(["completed", "auto_completed"]),
                 AttendanceSession.school_id == school_id).all()
        return [SessionDTO(id=s.id,
                           teacher_name=s.teacher.name if s.teacher else "?",
                           class_name=s.class_.name if s.class_ else "?",
                           class_id=s.class_id,
                           end_time=s.end_time,
                           absent=[(r.student.name, r.reason) for r in s.records if not r.is_present],
                           school_name=s.school.name if s.school else None,
                           status=s.status)
                for s in sessions]


def set_absence_reason(student_id: int, class_id: int, target_date: date,
                       reason: str, school_id: int) -> None:
    with get_db() as db:
        sess = db.query(AttendanceSession).filter(
            AttendanceSession.class_id == class_id,
            AttendanceSession.session_date == target_date,
            AttendanceSession.status.in_(["completed", "auto_completed"]),
            AttendanceSession.school_id == school_id,
        ).first()
        if not sess:
            return
        db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == sess.id,
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.is_present.is_(False),
        ).update({"reason": reason})


def get_absent_students_today(class_id: int, today_date: date,
                              school_id: int) -> dict[int, dict]:
    with get_db() as db:
        sess = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
        ).filter(AttendanceSession.class_id == class_id,
                 AttendanceSession.status.in_(["completed", "auto_completed"]),
                 AttendanceSession.session_date == today_date,
                 AttendanceSession.school_id == school_id).first()

        if not sess:
            return {}

        result: dict[int, dict] = {}
        for rec in sess.records:
            if not rec.is_present:
                result[rec.student_id] = {"name": rec.student.name, "reason": rec.reason}
        return result

def get_class_session_today(class_id: int, target_date: date, school_id: int) -> dict | None:
    with get_db() as db:
        sess = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.class_),
            joinedload(AttendanceSession.records),
        ).filter(
            AttendanceSession.class_id == class_id,
            AttendanceSession.session_date == target_date,
            AttendanceSession.school_id == school_id,
        ).first()
        if not sess:
            return None
        return {
            "id": sess.id,
            "class_id": sess.class_id,
            "class_name": sess.class_.name if sess.class_ else "?",
            "status": sess.status,
            "records": [
                {"student_id": r.student_id, "is_present": r.is_present, "reason": r.reason}
                for r in sess.records
            ],
        }


def update_session_records(
    session_id: int,
    updates: list[tuple[int, bool, str | None]],
) -> None:
    with get_db() as db:
        for student_id, is_present, reason in updates:
            db.query(AttendanceRecord).filter(
                AttendanceRecord.session_id == session_id,
                AttendanceRecord.student_id == student_id,
            ).update({"is_present": is_present, "reason": reason})


def is_class_done_today(class_id: int, today_date: date, school_id: int) -> bool:
    with get_db() as db:
        exists = db.query(AttendanceSession).filter(
            AttendanceSession.class_id == class_id,
            AttendanceSession.session_date == today_date,
            AttendanceSession.status.in_(["completed", "auto_completed"]),
            AttendanceSession.school_id == school_id,
        ).first()
        return exists is not None


def is_school_done_today(today_date: date, school_id: int) -> bool:
    with get_db() as db:
        classes_count = db.query(Class).filter(Class.school_id == school_id).count()
        if classes_count == 0:
            return False
        active_exists = db.query(AttendanceSession).filter(
            AttendanceSession.session_date == today_date,
            AttendanceSession.status == "active",
            AttendanceSession.school_id == school_id,
        ).first()
        return active_exists is None


def get_absence_reason_counts(target_date: date, school_id: int) -> dict[str, int]:
    from core.constants import DEFAULT_ABSENCE_REASON
    with get_db() as db:
        sessions = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.records),
        ).filter(
            AttendanceSession.session_date == target_date,
            AttendanceSession.status.in_(["completed", "auto_completed"]),
            AttendanceSession.school_id == school_id,
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


def reset_today_sessions(school_id: int) -> int:
    today = date.today()
    with get_db() as db:
        sessions = db.query(AttendanceSession).filter(
            AttendanceSession.session_date == today,
            AttendanceSession.school_id == school_id,
        ).all()
        count = len(sessions)
        for s in sessions:
            db.delete(s)
        return count


def get_teacher_session_today(teacher_id: int, today_date: date,
                              school_id: int) -> SessionDTO | None:
    with get_db() as db:
        s = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.teacher),
            joinedload(AttendanceSession.class_),
            joinedload(AttendanceSession.school),
            joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
        ).filter(
            AttendanceSession.teacher_id == teacher_id,
            AttendanceSession.session_date == today_date,
            AttendanceSession.school_id == school_id,
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
            school_name=s.school.name if s.school else None,
            status=s.status,
        )


def get_teachers_paginated(page: int, per_page: int, school_id: int):
    with get_db() as db:
        query = db.query(Teacher).options(joinedload(Teacher.school)).filter(
            Teacher.school_id == school_id
        )
        total = query.count()
        teachers = query.order_by(Teacher.name).offset((page - 1) * per_page).limit(per_page).all()
        result = [
            TeacherDTO(
                id=t.id, telegram_id=t.telegram_id, name=t.name,
                role=t.role, is_active=t.is_active,
                school_id=t.school_id,
                class_id=t.class_id,
                class_name=t.class_.name if t.class_ else None,
                school_name=t.school.name if t.school else None
            )
            for t in teachers
        ]
        return result, total


def get_students_by_class_paginated(class_id: int, page: int, per_page: int, school_id: int):
    with get_db() as db:
        query = db.query(Student).filter(
            Student.class_id == class_id,
            Student.school_id == school_id
        )
        total = query.count()
        students = query.order_by(Student.name).offset((page - 1) * per_page).limit(per_page).all()
        result = [StudentDTO(id=s.id, name=s.name, class_id=s.class_id) for s in students]
        return result, total


def get_class_teacher_for_class(class_id: int, school_id: int) -> TeacherDTO | None:
    with get_db() as db:
        t = db.query(Teacher).filter(
            Teacher.class_id == class_id,
            Teacher.role == "class_teacher",
            Teacher.school_id == school_id
        ).first()
        if not t:
            return None
        return TeacherDTO(
            id=t.id, telegram_id=t.telegram_id, name=t.name,
            role=t.role, is_active=t.is_active,
            school_id=t.school_id,
            class_id=t.class_id,
            class_name=t.class_.name if t.class_ else None,
            school_name=t.school.name if t.school else None
        )


# ===== Заявки на регистрацию =====

def get_pending_requests(school_id: int) -> list[dict]:
    from core.roles import ROLE_LABELS
    with get_db() as db:
        reqs = db.query(RegistrationRequest).filter(
            RegistrationRequest.status == "pending",
            RegistrationRequest.school_id == school_id
        ).all()
        return [{
            'id': r.id,
            'telegram_id': r.telegram_id,
            'name': r.name,
            'role': r.role,
            'role_label': ROLE_LABELS.get(r.role, r.role),
            'class_name': r.class_name,
        } for r in reqs]


def approve_request(req_id: int, school_id: int) -> bool:
    with get_db() as db:
        req = db.query(RegistrationRequest).filter(
            RegistrationRequest.id == req_id,
            RegistrationRequest.status == "pending",
            RegistrationRequest.school_id == school_id
        ).first()
        if not req:
            return False

        inactive_teacher = db.query(Teacher).filter(
            Teacher.telegram_id == req.telegram_id,
            Teacher.school_id == school_id,
            Teacher.is_active == False
        ).first()

        if inactive_teacher:
            inactive_teacher.is_active = True
            inactive_teacher.role = req.role
            inactive_teacher.name = req.name
            if req.class_name:
                c = db.query(Class).filter(Class.name == req.class_name,
                                           Class.school_id == school_id).first()
                if c:
                    inactive_teacher.class_id = c.id
            req.status = "approved"
            return True

        active_teacher = db.query(Teacher).filter(
            Teacher.telegram_id == req.telegram_id,
            Teacher.school_id == school_id,
            Teacher.is_active == True
        ).first()
        if active_teacher:
            req.status = "rejected"
            return False

        class_id = None
        if req.class_name:
            c = db.query(Class).filter(Class.name == req.class_name,
                                       Class.school_id == school_id).first()
            if c:
                class_id = c.id
        teacher = Teacher(
            telegram_id=req.telegram_id,
            name=req.name,
            role=req.role,
            class_id=class_id,
            school_id=school_id,
        )
        db.add(teacher)
        req.status = "approved"
        return True


def reject_request(req_id: int, school_id: int) -> None:
    with get_db() as db:
        req = db.query(RegistrationRequest).filter(
            RegistrationRequest.id == req_id,
            RegistrationRequest.status == "pending",
            RegistrationRequest.school_id == school_id
        ).first()
        if req:
            req.status = "rejected"


def has_pending_request(telegram_id: int, school_id: int) -> bool:
    with get_db() as db:
        return db.query(RegistrationRequest).filter(
            RegistrationRequest.telegram_id == telegram_id,
            RegistrationRequest.school_id == school_id,
            RegistrationRequest.status == "pending",
        ).first() is not None


# ===== Питание =====

@dataclass
class MealItemDTO:
    student_id: int
    name: str
    meal_type: str
    is_eating: bool


@dataclass
class MealRequestDTO:
    class_id: int
    class_name: str
    items: list[MealItemDTO]


def get_or_create_meal_request(class_id: int, school_id: int) -> MealRequestDTO:
    today = date.today()
    with get_db() as db:
        req = db.query(MealRequest).filter(
            MealRequest.class_id == class_id,
            MealRequest.request_date == today,
            MealRequest.school_id == school_id,
        ).first()
        if req:
            items = [MealItemDTO(
                student_id=i.student_id,
                name=i.student.name,
                meal_type=i.meal_type,
                is_eating=i.is_eating,
            ) for i in req.items]
            return MealRequestDTO(class_id=class_id, class_name=req.class_.name, items=items)

        students = db.query(Student).filter(
            Student.class_id == class_id,
            Student.school_id == school_id,
        ).order_by(Student.name).all()
        items = [MealItemDTO(
            student_id=s.id,
            name=s.name,
            meal_type=s.meal_type,
            is_eating=True,
        ) for s in students]
        return MealRequestDTO(
            class_id=class_id,
            class_name=db.query(Class).filter(Class.id == class_id).first().name,
            items=items,
        )


def is_meal_request_exists(class_id: int, request_date: date, school_id: int) -> bool:
    with get_db() as db:
        return db.query(MealRequest).filter(
            MealRequest.class_id == class_id,
            MealRequest.request_date == request_date,
            MealRequest.school_id == school_id,
        ).first() is not None


def save_meal_request(class_id: int, teacher_id: int,
                      items: list[MealItemDTO], school_id: int) -> MealRequest:
    today = date.today()
    with get_db() as db:
        req = db.query(MealRequest).filter(
            MealRequest.class_id == class_id,
            MealRequest.request_date == today,
            MealRequest.school_id == school_id,
        ).first()
        if req:
            db.query(MealRequestItem).filter(MealRequestItem.request_id == req.id).delete()
            for item in items:
                db.add(MealRequestItem(
                    request_id=req.id,
                    student_id=item.student_id,
                    is_eating=item.is_eating,
                    meal_type=item.meal_type,
                ))
            req.submitted_at = datetime.now()
            req.submitted_by_id = teacher_id
            db.flush()
            return req
        else:
            req = MealRequest(
                class_id=class_id,
                request_date=today,
                submitted_by_id=teacher_id,
                school_id=school_id,
            )
            db.add(req)
            db.flush()
            for item in items:
                db.add(MealRequestItem(
                    request_id=req.id,
                    student_id=item.student_id,
                    is_eating=item.is_eating,
                    meal_type=item.meal_type,
                ))
            db.flush()
            return req


def update_student_meal_type(student_id: int, meal_type: str) -> None:
    with get_db() as db:
        st = db.query(Student).filter(Student.id == student_id).first()
        if st:
            st.meal_type = meal_type
            db.flush()


def get_chef_telegram_ids(school_id: int) -> list[int]:
    with get_db() as db:
        chefs = db.query(Teacher.telegram_id).filter(
            Teacher.school_id == school_id,
            Teacher.role == "chef",
            Teacher.is_active == True,
        ).all()
        return [c[0] for c in chefs]


def get_meal_summary(school_id: int, target_date: date | None = None) -> str:
    if target_date is None:
        target_date = date.today()
    with get_db() as db:
        classes = db.query(Class).filter(
            Class.school_id == school_id
        ).order_by(Class.grade, Class.letter).all()

        requests = db.query(MealRequest).options(
            joinedload(MealRequest.class_),
            joinedload(MealRequest.submitted_by),
            joinedload(MealRequest.items),
        ).filter(
            MealRequest.school_id == school_id,
            MealRequest.request_date == target_date,
        ).all()

        if not requests:
            return f"🍽️ На {target_date.strftime('%d.%m.%Y')} заявок нет."

        requests_by_class = {req.class_id: req for req in requests}
        primary_lines = []
        senior_lines = []

        for cls in classes:
            grade = cls.grade or 0
            req = requests_by_class.get(cls.id)

            if req:
                eating_items = [i for i in req.items if i.is_eating]
                total = len(eating_items)
                paid = sum(1 for i in eating_items if i.meal_type == "paid")
                free = total - paid
                teacher_name = req.submitted_by.name if req.submitted_by else "—"
                line = f"{cls.name}: всего {total} (платно {paid}, бесплатно {free}) — {teacher_name}"
            else:
                line = f"{cls.name}: —"

            if 1 <= grade <= 4:
                primary_lines.append(line)
            else:
                senior_lines.append(line)

        lines = [f"🍽️ Питание на {target_date.strftime('%d.%m.%Y')}"]
        if primary_lines:
            lines.append("")
            lines.append("🟢 1–4 классы")
            lines.extend(primary_lines)
        if senior_lines:
            lines.append("")
            lines.append("🔵 5–11 классы")
            lines.extend(senior_lines)

        return "\n".join(lines)


def get_free_meals_report(school_id: int, target_date: date | None = None) -> str:
    if target_date is None:
        target_date = date.today()

    with get_db() as db:
        classes = db.query(Class).filter(
            Class.school_id == school_id
        ).order_by(Class.grade, Class.letter).all()

        requests = db.query(MealRequest).options(
            joinedload(MealRequest.items).joinedload(MealRequestItem.student)
        ).filter(
            MealRequest.school_id == school_id,
            MealRequest.request_date == target_date,
        ).all()

        req_by_class = {req.class_id: req for req in requests}
        lines = [f"🆓 Отчет по питающимся \"бесплатно\" на {target_date.strftime('%d.%m.%Y')}"]
        has_any = False

        for cls in classes:
            req = req_by_class.get(cls.id)
            if not req:
                continue

            free_students = [
                item.student.name
                for item in req.items
                if item.is_eating and item.meal_type == "free"
            ]

            if free_students:
                has_any = True
                lines.append(f"\n{cls.name}")
                for name in sorted(free_students):
                    lines.append(name)

        if not has_any:
            return f"🆓 На {target_date.strftime('%d.%m.%Y')} бесплатников нет."

        return "\n".join(lines)

# ===== Аналитика по классу =====

def get_class_analytics(class_id: int, school_id: int,
                        date_from: date, date_to: date) -> dict:
    from collections import Counter, defaultdict
    from core.constants import DEFAULT_ABSENCE_REASON

    with get_db() as db:
        students_all = (
            db.query(Student.id, Student.name)
            .filter(
                Student.class_id == class_id,
                Student.school_id == school_id,
            )
            .order_by(Student.name)
            .all()
        )

        rows = (
            db.query(AttendanceRecord.student_id, AttendanceRecord.reason)
            .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
            .filter(
                AttendanceSession.class_id == class_id,
                AttendanceSession.school_id == school_id,
                AttendanceSession.status.in_(["completed", "auto_completed"]),
                AttendanceSession.session_date >= date_from,
                AttendanceSession.session_date <= date_to,
                AttendanceRecord.is_present.is_(False),
            )
            .all()
        )

        by_student: dict[int, Counter] = defaultdict(Counter)
        by_reason_total: Counter = Counter()

        for student_id, reason in rows:
            r = reason or DEFAULT_ABSENCE_REASON
            by_student[student_id][r] += 1
            by_reason_total[r] += 1

        students = []
        for s_id, s_name in students_all:
            reasons = dict(by_student.get(s_id, {}))
            total = sum(reasons.values())
            students.append({
                "id": s_id,
                "name": s_name,
                "total": total,
                "by_reason": reasons,
            })

        with_absences = [s for s in students if s["total"] > 0]
        top_students = sorted(with_absences, key=lambda x: -x["total"])[:5]

        top_student = None
        if top_students:
            top_student = {"name": top_students[0]["name"], "count": top_students[0]["total"]}

        top_reason = None
        if by_reason_total:
            name, count = by_reason_total.most_common(1)[0]
            top_reason = {"name": name, "count": count}

        return {
            "students": students,
            "by_reason": dict(by_reason_total),
            "top_students": top_students,
            "top_student": top_student,
            "top_reason": top_reason,
            "total_absences": len(rows),
        }


def get_class_quarters_with_data(class_id: int, school_id: int,
                                 quarters: list[dict]) -> list[dict]:
    if not quarters:
        return []
    with get_db() as db:
        result = []
        for q in quarters:
            count = (
                db.query(AttendanceRecord.id)
                .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
                .filter(
                    AttendanceSession.class_id == class_id,
                    AttendanceSession.school_id == school_id,
                    AttendanceSession.status.in_(["completed", "auto_completed"]),
                    AttendanceSession.session_date >= q["date_from"],
                    AttendanceSession.session_date <= q["date_to"],
                    AttendanceRecord.is_present.is_(False),
                )
                .count()
            )
            result.append({**q, "total_absences": count})
        return result


def get_class_meal_summary(class_id: int, school_id: int,
                           target_date: date | None = None) -> str:
    if target_date is None:
        target_date = date.today()
    with get_db() as db:
        req = db.query(MealRequest).options(
            joinedload(MealRequest.items),
        ).filter(
            MealRequest.class_id == class_id,
            MealRequest.school_id == school_id,
            MealRequest.request_date == target_date,
        ).first()
        if not req:
            return "Заявка не найдена."
        eating_items = [i for i in req.items if i.is_eating]
        total = len(eating_items)
        paid = sum(1 for i in eating_items if i.meal_type == "paid")
        free = total - paid
        return f"🔄 Обновление {req.class_.name}: всего {total} (платно {paid}, бесплатно {free})"


def get_absences_export_data(school_id: int, class_id: int = None, date_from: date = None,
                             date_to: date = None) -> dict:
    from core.constants import ABSENCE_REASONS, DEFAULT_ABSENCE_REASON

    sick_str = ABSENCE_REASONS[0]
    statement_str = ABSENCE_REASONS[1]
    recuperation_str = ABSENCE_REASONS[2]
    unexcused_str = ABSENCE_REASONS[3]

    with get_db() as db:
        q_classes = db.query(Class).filter(Class.school_id == school_id)
        if class_id:
            q_classes = q_classes.filter(Class.id == class_id)
        classes = q_classes.order_by(Class.grade, Class.letter).all()

        result = {}

        for cls in classes:
            students = db.query(Student).filter(
                Student.class_id == cls.id
            ).order_by(Student.name).all()

            class_data = []
            for student in students:
                q_records = db.query(AttendanceRecord).join(AttendanceSession).filter(
                    AttendanceRecord.student_id == student.id,
                    AttendanceSession.status.in_(["completed", "auto_completed"])
                )
                if date_from:
                    q_records = q_records.filter(AttendanceSession.session_date >= date_from)
                if date_to:
                    q_records = q_records.filter(AttendanceSession.session_date <= date_to)

                records = q_records.all()

                absent_records = [r for r in records if not r.is_present]
                total = len(absent_records)

                sick = sum(1 for r in absent_records if r.reason == sick_str)
                statement = sum(1 for r in absent_records if r.reason == statement_str)
                recuperation = sum(1 for r in absent_records if r.reason == recuperation_str)
                unexcused = sum(1 for r in absent_records if
                                r.reason == unexcused_str or r.reason is None or r.reason == DEFAULT_ABSENCE_REASON)

                class_data.append({
                    "name": student.name,
                    "total": total,
                    "sick": sick,
                    "statement": statement,
                    "recuperation": recuperation,
                    "unexcused": unexcused,
                })

            if class_data:
                result[cls.name] = class_data

        return result

# ===== Охват питания =====

_MONTH_NAMES_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


def get_meal_coverage_months(school_id: int) -> list[dict]:
    with get_db() as db:
        rows = (
            db.query(
                extract("year", AttendanceSession.session_date).label("y"),
                extract("month", AttendanceSession.session_date).label("m"),
            )
            .filter(
                AttendanceSession.school_id == school_id,
                AttendanceSession.status.in_(["completed", "auto_completed"]),
            )
            .distinct()
            .all()
        )
    seen = {(int(y), int(m)) for y, m in rows if y and m}
    return [
        {"year": y, "month": m, "label": f"{_MONTH_NAMES_RU[m - 1]} {y}"}
        for (y, m) in sorted(seen, reverse=True)
    ]


def get_meal_coverage(year: int, month: int, school_id: int) -> dict:
    label = f"{_MONTH_NAMES_RU[month - 1]} {year}"

    primary_dates: set = set()
    senior_dates: set = set()
    primary_absences = 0
    senior_absences = 0

    with get_db() as db:
        sessions = (
            db.query(AttendanceSession)
            .options(
                joinedload(AttendanceSession.records),
                joinedload(AttendanceSession.class_),
            )
            .filter(
                AttendanceSession.school_id == school_id,
                AttendanceSession.status.in_(["completed", "auto_completed"]),
                extract("year", AttendanceSession.session_date) == year,
                extract("month", AttendanceSession.session_date) == month,
            )
            .all()
        )

        for s in sessions:
            grade = s.class_.grade if s.class_ else 0
            absences = sum(1 for r in s.records if not r.is_present)
            if grade and 1 <= grade <= 4:
                primary_dates.add(s.session_date)
                primary_absences += absences
            else:
                senior_dates.add(s.session_date)
                senior_absences += absences

    days_primary = len(primary_dates)
    days_senior = len(senior_dates)
    coef_primary = primary_absences / days_primary if days_primary else 0.0
    coef_senior = senior_absences / days_senior if days_senior else 0.0

    return {
        "year": year, "month": month, "label": label,
        "primary": {
            "days": days_primary,
            "absences": primary_absences,
            "coefficient": coef_primary,
        },
        "senior": {
            "days": days_senior,
            "absences": senior_absences,
            "coefficient": coef_senior,
        },
    }


# ===== Школы (глобальные) =====

def get_all_schools() -> list[dict]:
    with get_db() as db:
        schools = db.query(School).all()
        return [{"id": s.id, "name": s.name} for s in schools]


def create_school(name: str) -> dict:
    with get_db() as db:
        school = School(name=name)
        db.add(school)
        db.flush()
        return {"id": school.id, "name": school.name}


def ensure_admin_teacher(telegram_id: int, school_id: int) -> None:
    with get_db() as db:
        existing = db.query(Teacher).filter(
            Teacher.telegram_id == telegram_id,
            Teacher.school_id == school_id,
        ).first()
        if not existing:
            db.add(Teacher(
                telegram_id=telegram_id,
                name="Администратор",
                role="admin",
                school_id=school_id,
                is_active=True,
            ))

# ===== Интеграция с СКУД Sigur =====

def get_teacher_by_card_number(card_number: str, school_id: int) -> TeacherDTO | None:
    with get_db() as db:
        t = db.query(Teacher).options(joinedload(Teacher.school)).filter(
            Teacher.card_number == card_number,
            Teacher.school_id == school_id,
            Teacher.is_active == True
        ).first()
        if not t:
            return None
        return TeacherDTO(
            id=t.id, telegram_id=t.telegram_id, name=t.name,
            role=t.role, is_active=t.is_active,
            school_id=t.school_id,
            class_id=t.class_id,
            class_name=t.class_.name if t.class_ else None,
            school_name=t.school.name if t.school else None
        )

def update_teacher_status(teacher_id: int, is_inside: bool) -> None:
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if t:
            t.is_inside = is_inside
            db.commit()