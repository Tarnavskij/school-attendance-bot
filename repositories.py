# repositories.py
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from sqlalchemy import or_
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
    marked_by_teacher_id: int | None = None


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
    # ── Multi-teacher ────────────────────────────────────────────────────────
    participant_ids: list[int] | None = None
    participant_names: list[str] | None = None
    finalize_at: datetime | None = None
    editor_teacher_id: int | None = None


@dataclass
class CreatedSession:
    id: int


class SessionAlreadyExists(Exception):
    pass


# ===== Учителя (требуют school_id) =====


def get_default_school_id() -> int:
    """Возвращает ID первой школы в БД. Если школ нет – создаёт дефолтную."""
    with get_db() as db:
        school = db.query(School).first()
        if school:
            return school.id
        # Если школ нет – создаём (аналогично web_viewer.py)
        new_school = School(name="Основная школа")
        db.add(new_school)
        db.commit()
        return new_school.id

def get_teacher_by_telegram_id(telegram_id: int) -> TeacherDTO | None:
    """Возвращает активного учителя в любой школе."""
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
    """Физическое удаление учителя и всех его заявок в этой школе."""
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


def get_available_classes(today_date: date, school_id: int, teacher_id: int) -> list[ClassDTO]:
    """
    Возвращает классы, доступные конкретному учителю для начала переклички.

    Правила:
      - Нет сессии за сегодня → класс доступен.
      - active (кто-то сейчас отмечает) → НЕ показывать никому.
      - partial (A отправил подгруппу, ждём B):
          показывать только тем, кто НЕ участвовал.
      - completed / auto_completed → НЕ показывать.
    """
    with get_db() as db:
        # Все классы школы
        all_classes = (
            db.query(Class)
            .filter(Class.school_id == school_id)
            .order_by(Class.grade, Class.letter)
            .all()
        )
        # Все сегодняшние сессии школы
        sessions = (
            db.query(AttendanceSession)
            .filter(
                AttendanceSession.session_date == today_date,
                AttendanceSession.school_id == school_id,
            )
            .all()
        )

    # Разбор сессий по классам
    sessions_by_class: dict[int, list] = {}
    for s in sessions:
        sessions_by_class.setdefault(s.class_id, []).append(s)

    result: list[ClassDTO] = []
    for c in all_classes:
        cls_sessions = sessions_by_class.get(c.id, [])

        # Нет сессии → доступен
        if not cls_sessions:
            result.append(ClassDTO(
                id=c.id, name=c.name, school_id=c.school_id,
                grade=c.grade, letter=c.letter,
            ))
            continue

        # Есть хотя бы одна сессия. Берём её (за сегодня их не может быть > 1 по UNIQUE,
        # но список — на всякий случай).
        s = cls_sessions[0]

        if s.status == "active":
            # Занят кем-то — никому не показываем
            continue

        if s.status == "partial":
            # Показываем только тем, кто не участвовал
            participant_ids = s.participant_ids or []
            if teacher_id in participant_ids:
                continue
            if s.teacher_id == teacher_id:
                continue
            result.append(ClassDTO(
                id=c.id, name=c.name, school_id=c.school_id,
                grade=c.grade, letter=c.letter,
            ))
            continue

        # completed / auto_completed / что-то ещё — не показываем
        continue

    return result


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
    """
    Возвращает сессию за указанную дату для класса (любого статуса) или None.

    Формат:
      {
        "id": int,
        "class_id": int,
        "class_name": str,
        "status": str,
        "teacher_id": int | None,
        "editor_teacher_id": int | None,
        "participant_ids": list[int],
        "participant_names": list[str],
        "finalize_at": datetime | None,
        "records": [
          {
            "student_id": int,
            "is_present": bool,
            "reason": str | None,
            "marked_by_teacher_id": int | None,
          }, ...
        ],
      }
    """
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

        # Собираем participant_ids (JSON-поле может быть None)
        participant_ids: list[int] = list(sess.participant_ids or [])

        # Имена участников — одним запросом
        participant_names: list[str] = []
        if participant_ids:
            teachers = (
                db.query(Teacher)
                .filter(Teacher.id.in_(participant_ids))
                .all()
            )
            names_by_id = {t.id: t.name for t in teachers}
            for tid in participant_ids:
                participant_names.append(names_by_id.get(tid, f"Учитель #{tid}"))

        return {
            "id": sess.id,
            "class_id": sess.class_id,
            "class_name": sess.class_.name if sess.class_ else "?",
            "status": sess.status,
            "teacher_id": sess.teacher_id,
            "editor_teacher_id": sess.editor_teacher_id,
            "participant_ids": participant_ids,
            "participant_names": participant_names,
            "finalize_at": sess.finalize_at,
            "records": [
                {
                    "student_id": r.student_id,
                    "is_present": r.is_present,
                    "reason": r.reason,
                    "marked_by_teacher_id": r.marked_by_teacher_id,
                }
                for r in sess.records
            ],
        }


def update_session_records(
    session_id: int,
    updates: list[tuple[int, bool, str | None]],
) -> None:
    """
    Массовое обновление записей сессии.
    updates: список кортежей (student_id, is_present, reason).
    """
    with get_db() as db:
        for student_id, is_present, reason in updates:
            db.query(AttendanceRecord).filter(
                AttendanceRecord.session_id == session_id,
                AttendanceRecord.student_id == student_id,
            ).update({"is_present": is_present, "reason": reason})

# ── Multi-teacher: серверный lock редактирования ─────────────────────────────

# Результаты try_acquire_editor_lock
LOCK_ACQUIRED = "acquired"
LOCK_ALREADY_OWNED = "already_owned"
LOCK_BUSY = "busy"
LOCK_CLOSED = "closed"


def try_acquire_editor_lock(session_id: int, teacher_id: int) -> str:
    """
    Атомарно пытается поставить lock редактирования на сессию.

    Возвращает один из:
      - LOCK_ACQUIRED      — lock наш
      - LOCK_ALREADY_OWNED — lock уже наш (idempotent re-entry)
      - LOCK_BUSY          — lock занят другим, ещё не протух
      - LOCK_CLOSED        — сессия не найдена

    Реализация — один UPDATE с WHERE, без SELECT→IF→UPDATE.
    TTL считается в Python (cutoff), чтобы работало и на SQLite, и на PostgreSQL.
    """
    from config import EDIT_LOCK_TTL_MINUTES
    now = datetime.now()
    cutoff = now - timedelta(minutes=EDIT_LOCK_TTL_MINUTES)

    with get_db() as db:
        # Сначала посмотрим, есть ли сессия и кто текущий держатель.
        # Это НЕ для принятия решения — просто чтобы понять, мы уже owner или busy.
        s = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
        if not s:
            return LOCK_CLOSED

        # Атомарный UPDATE: забираем lock, если он пуст / протух / наш.
        updated = (
            db.query(AttendanceSession)
            .filter(
                AttendanceSession.id == session_id,
                or_(
                    AttendanceSession.editor_teacher_id.is_(None),
                    AttendanceSession.editor_locked_at < cutoff,
                    AttendanceSession.editor_teacher_id == teacher_id,
                ),
            )
            .update(
                {
                    "editor_teacher_id": teacher_id,
                    "editor_locked_at": now,
                },
                synchronize_session=False,
            )
        )

        if updated == 1:
            # Если owner был уже мы — это idempotent re-entry
            if s.editor_teacher_id == teacher_id:
                return LOCK_ALREADY_OWNED
            return LOCK_ACQUIRED

        # Ни одна строка не обновлена → lock занят другим и не протух
        return LOCK_BUSY


def release_editor_lock(session_id: int, teacher_id: int) -> None:
    """
    Снимает lock, если он принадлежит teacher_id.
    Не снимает чужой lock — на случай гонки.
    """
    with get_db() as db:
        db.query(AttendanceSession).filter(
            AttendanceSession.id == session_id,
            AttendanceSession.editor_teacher_id == teacher_id,
        ).update(
            {"editor_teacher_id": None, "editor_locked_at": None},
            synchronize_session=False,
        )


def force_release_editor_lock(session_id: int) -> None:
    """
    Принудительно снимает lock. Используется scheduler'ом
    при автозакрытии сессии (10:00 / 20:00 / 45 минут).
    """
    with get_db() as db:
        db.query(AttendanceSession).filter(
            AttendanceSession.id == session_id,
        ).update(
            {"editor_teacher_id": None, "editor_locked_at": None},
            synchronize_session=False,
        )


def get_editor_info(session_id: int) -> dict | None:
    """
    Возвращает {'teacher_id': int, 'name': str} текущего держателя lock
    или None, если lock свободен/протух/сессии нет.
    """
    from config import EDIT_LOCK_TTL_MINUTES
    cutoff = datetime.now() - timedelta(minutes=EDIT_LOCK_TTL_MINUTES)

    with get_db() as db:
        s = db.query(AttendanceSession).options(
            joinedload(AttendanceSession.editor),
        ).filter(AttendanceSession.id == session_id).first()
        if not s or s.editor_teacher_id is None:
            return None
        # Протух?
        if s.editor_locked_at is None or s.editor_locked_at < cutoff:
            return None
        name = s.editor.name if s.editor else f"Учитель #{s.editor_teacher_id}"
        return {"teacher_id": s.editor_teacher_id, "name": name}

# ── Multi-teacher: проверка deadline редактирования ──────────────────────────

def check_edit_deadline(session_id: int) -> tuple[bool, str]:
    """
    Единая проверка: можно ли сейчас редактировать сессию.

    Возвращает (True, "") если можно,
    или (False, причина) если нельзя.

    Причины:
      - "session_not_found" — сессии нет
      - "session_closed"    — статус не поддерживает редактирование
      - "deadline_expired"  — истёк finalize_at
    """
    with get_db() as db:
        s = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
        if not s:
            return False, "session_not_found"

        # auto_completed — read-only всегда
        if s.status == "auto_completed":
            return False, "session_closed"

        # finalize_at — общий дедлайн для completed
        # (для partial finalize_at тоже проставлен — это дедлайн первой отправки)
        if s.finalize_at is not None and datetime.now() >= s.finalize_at:
            return False, "deadline_expired"

        return True, ""

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
    """
    True, если школа «готова»: нет ни одной active, ни одной partial.
    Считаем незавершёнными обе стадии — пока класс не закрыт окончательно,
    секретарь видит «Перекличка в процессе».
    """
    with get_db() as db:
        classes_count = db.query(Class).filter(Class.school_id == school_id).count()
        if classes_count == 0:
            return False
        pending_exists = db.query(AttendanceSession).filter(
            AttendanceSession.session_date == today_date,
            AttendanceSession.school_id == school_id,
            AttendanceSession.status.in_(["active", "partial"]),
        ).first()
        return pending_exists is None


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
    """
    Возвращает сессию за сегодня, в которой участвовал учитель:
    либо он создатель (teacher_id), либо он в participant_ids.

    Если найдено несколько — вернуть первую в детерминированном порядке
    (по id). По решению ТЗ вклад «несколько partial за день» отложен,
    и мы показываем первую.
    """
    with get_db() as db:
        # Достаём все сегодняшние сессии учителя, фильтруем participant_ids в Python.
        candidates = (
            db.query(AttendanceSession)
            .options(
                joinedload(AttendanceSession.teacher),
                joinedload(AttendanceSession.class_),
                joinedload(AttendanceSession.school),
                joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
            )
            .filter(
                AttendanceSession.session_date == today_date,
                AttendanceSession.school_id == school_id,
            )
            .order_by(AttendanceSession.id)
            .all()
        )

        target = None
        for s in candidates:
            if s.teacher_id == teacher_id:
                target = s
                break
            pids = s.participant_ids or []
            if teacher_id in pids:
                target = s
                break

        if not target:
            return None

        return SessionDTO(
            id=target.id,
            teacher_name=target.teacher.name if target.teacher else "?",
            class_name=target.class_.name if target.class_ else "?",
            class_id=target.class_id,
            end_time=target.end_time,
            absent=[(r.student.name, r.reason) for r in target.records if not r.is_present],
            school_name=target.school.name if target.school else None,
            status=target.status,
            participant_ids=list(target.participant_ids or []),
            finalize_at=target.finalize_at,
            editor_teacher_id=target.editor_teacher_id,
        )

# ── Multi-teacher: участники сессии ──────────────────────────────────────────

def add_participant(session_id: int, teacher_id: int) -> None:
    """
    Добавляет teacher_id в participant_ids сессии (без дублей).
    Если уже есть — ничего не делает.
    Максимум 2 участника (3+ отложено, см. ТЗ).
    """
    with get_db() as db:
        s = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
        if not s:
            return
        pids = list(s.participant_ids or [])
        if teacher_id in pids:
            return
        # Защита от «3+ участников» — как решили в ТЗ, сейчас не поддерживаем
        if len(pids) >= 2:
            return
        pids.append(teacher_id)
        # Важно: reassign — SQLAlchemy не отслеживает мутации list in-place
        s.participant_ids = pids


# ── Multi-teacher: ownership конкретных отметок ──────────────────────────────

def set_marked_by_on_submit(
    session_id: int,
    teacher_id: int,
    student_ids: list[int],
) -> None:
    """
    Проставляет marked_by_teacher_id = teacher_id для указанных записей.
    Используется при submit в partial-режиме: A фиксирует свои ❌,
    B фиксирует свои ❌.

    student_ids — только те, кого этот учитель явно перевёл в ❌.
    """
    if not student_ids:
        return
    with get_db() as db:
        db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == session_id,
            AttendanceRecord.student_id.in_(student_ids),
        ).update(
            {"marked_by_teacher_id": teacher_id},
            synchronize_session=False,
        )


def clear_marked_by(session_id: int) -> None:
    """
    Сбрасывает все marked_by_teacher_id в NULL для сессии.
    Используется при переходе в completed: после закрытия ownership
    больше не ограничивает редактирование.
    """
    with get_db() as db:
        db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == session_id,
        ).update(
            {"marked_by_teacher_id": None},
            synchronize_session=False,
        )

# ── Multi-teacher: атомарный save ────────────────────────────────────────────

def save_attendance_transactional(
    session_id: int,
    teacher_id: int,
    all_records: list[tuple[int, bool, str | None]],
    changed_student_ids: list[int],
    target_status: str,
    mode: str,
) -> tuple[bool, str]:
    """
    Единая атомарная операция сохранения изменений в сессии.

    Аргументы:
      session_id          — id сессии
      teacher_id          — id учителя, который сохраняет
      all_records         — полный массив (student_id, is_present, reason)
                            для записи в БД
      changed_student_ids — id учеников, которых текущий учитель явно изменил
                            за этот заход (нужно для ownership)
      target_status       — "partial" или "completed"
      mode                — "new_all" | "new_partial" | "partial_join"

    Возвращает (True, "") при успехе или (False, причина):
      - "session_not_found"
      - "lock_busy"
      - "deadline_expired"
      - "session_closed"
    """
    from config import EDIT_WINDOW_MINUTES, EDIT_LOCK_TTL_MINUTES
    now = datetime.now()
    cutoff = now - timedelta(minutes=EDIT_LOCK_TTL_MINUTES)

    with get_db() as db:
        s = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
        if not s:
            return False, "session_not_found"

        # 1) Lock: он должен быть наш (или пуст / протух)
        if s.editor_teacher_id not in (None, teacher_id):
            if s.editor_locked_at is not None and s.editor_locked_at >= cutoff:
                return False, "lock_busy"

        # 2) Deadline
        if s.finalize_at is not None and now >= s.finalize_at:
            return False, "deadline_expired"

        # 3) Статус
        if mode in ("new_all", "new_partial") and s.status != "active":
            return False, "session_closed"
        if mode == "partial_join" and s.status != "partial":
            return False, "session_closed"

        # 4) Применяем all_records
        for student_id, is_present, reason in all_records:
            db.query(AttendanceRecord).filter(
                AttendanceRecord.session_id == session_id,
                AttendanceRecord.student_id == student_id,
            ).update(
                {"is_present": is_present, "reason": reason},
                synchronize_session=False,
            )

        # 5) Ownership — только для изменённых записей
        if changed_student_ids:
            records_after = db.query(AttendanceRecord).filter(
                AttendanceRecord.session_id == session_id,
                AttendanceRecord.student_id.in_(changed_student_ids),
            ).all()
            for r in records_after:
                if r.is_present:
                    r.marked_by_teacher_id = None
                else:
                    r.marked_by_teacher_id = teacher_id

        # 6) При completed — ownership больше не ограничивает, обнуляем всё
        if target_status == "completed":
            db.query(AttendanceRecord).filter(
                AttendanceRecord.session_id == session_id,
            ).update(
                {"marked_by_teacher_id": None},
                synchronize_session=False,
            )

        # 7) participant_ids
        pids = list(s.participant_ids or [])
        if teacher_id not in pids:
            pids.append(teacher_id)
        s.participant_ids = pids

        # 8) Статус, end_time, finalize_at
        s.status = target_status
        if target_status == "completed":
            s.end_time = now
            if s.finalize_at is None:
                s.finalize_at = now + timedelta(minutes=EDIT_WINDOW_MINUTES)
        else:
            if s.finalize_at is None:
                s.finalize_at = now + timedelta(minutes=EDIT_WINDOW_MINUTES)

        # 9) Снимаем lock — всё в одной транзакции
        s.editor_teacher_id = None
        s.editor_locked_at = None

    return True, ""

# ── Multi-teacher: закрытие сессий по расписанию ─────────────────────────────

def close_partial_sessions(school_id: int | None = None) -> list[dict]:
    """
    Для cron-джоба 10:00.
    Все partial → completed. Active не трогает.

    Возвращает список сессий, для которых нужно отправить уведомление:
      [{"session_id": int, "class_id": int, "school_id": int,
        "participant_ids": list[int]}, ...]

    НЕ выставляет notify_sent — это делает scheduler после успешной отправки.
    """
    now = datetime.now()
    result: list[dict] = []

    with get_db() as db:
        q = db.query(AttendanceSession).filter(AttendanceSession.status == "partial")
        if school_id is not None:
            q = q.filter(AttendanceSession.school_id == school_id)
        sessions = q.all()

        for s in sessions:
            s.status = "completed"
            s.end_time = now
            s.editor_teacher_id = None
            s.editor_locked_at = None
            # finalize_at не трогаем — он уже проставлен при submit
            result.append({
                "session_id": s.id,
                "class_id": s.class_id,
                "school_id": s.school_id,
                "participant_ids": list(s.participant_ids or []),
            })

    return result


def finalize_due_sessions(school_id: int | None = None) -> list[dict]:
    """
    Для ежеминутного cron-джоба.
    Ищет сессии с finalize_at <= now AND notify_sent = False.

    Обработка по статусу:
      - partial    → completed (end_time, release lock)
      - completed  → статус не меняем, но нужен retry уведомления
      - active     → аварийный случай (не должно быть), закрываем как auto_completed

    Возвращает список сессий для уведомления:
      [{"session_id": int, "class_id": int, "school_id": int,
        "participant_ids": list[int], "status": str}, ...]

    НЕ выставляет notify_sent — это делает scheduler после отправки.
    """
    now = datetime.now()
    result: list[dict] = []

    with get_db() as db:
        q = (
            db.query(AttendanceSession)
            .filter(
                AttendanceSession.finalize_at.isnot(None),
                AttendanceSession.finalize_at <= now,
                AttendanceSession.notify_sent == False,
            )
        )
        if school_id is not None:
            q = q.filter(AttendanceSession.school_id == school_id)
        sessions = q.all()

        for s in sessions:
            if s.status == "partial":
                s.status = "completed"
                s.end_time = now
                s.editor_teacher_id = None
                s.editor_locked_at = None
            elif s.status == "active":
                # Защита от битых данных: finalize_at не должен стоять у active
                s.status = "auto_completed"
                s.editor_teacher_id = None
                s.editor_locked_at = None
            # completed — статус не меняем, только notification retry

            result.append({
                "session_id": s.id,
                "class_id": s.class_id,
                "school_id": s.school_id,
                "participant_ids": list(s.participant_ids or []),
                "status": s.status,
            })

    return result


def mark_notify_sent(session_id: int) -> None:
    """
    Помечает сессию как «уведомление отправлено».
    Вызывается scheduler'ом ПОСЛЕ успешного bot.send_message.
    При ошибке отправки — не вызывается, и retry произойдёт на следующей минуте.
    """
    with get_db() as db:
        db.query(AttendanceSession).filter(
            AttendanceSession.id == session_id,
        ).update(
            {"notify_sent": True},
            synchronize_session=False,
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
        # Все классы школы в порядке возрастания (1А, 1Б, 1В, 2А, ... 11Б)
        classes = db.query(Class).filter(
            Class.school_id == school_id
        ).order_by(Class.grade, Class.letter).all()

        # Все заявки на дату
        requests = db.query(MealRequest).options(
            joinedload(MealRequest.class_),
            joinedload(MealRequest.submitted_by),
            joinedload(MealRequest.items),
        ).filter(
            MealRequest.school_id == school_id,
            MealRequest.request_date == target_date,
        ).all()

        # Если на дату ни одной заявки — короткое сообщение
        if not requests:
            return f"🍽️ На {target_date.strftime('%d.%m.%Y')} заявок нет."

        # Заявки по class_id — для быстрого поиска при обходе классов
        requests_by_class = {req.class_id: req for req in requests}

        primary_lines = []   # 1–4 классы
        senior_lines = []    # 5–11 классы

        for cls in classes:
            grade = cls.grade or 0
            req = requests_by_class.get(cls.id)

            if req:
                # ФИЛЬТРУЕМ ТОЛЬКО ТЕХ, КТО ЕСТ
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
        # ФИЛЬТРУЕМ ТОЛЬКО ТЕХ, КТО ЕСТ
        eating_items = [i for i in req.items if i.is_eating]
        total = len(eating_items)
        paid = sum(1 for i in eating_items if i.meal_type == "paid")
        free = total - paid
        return f"🔄 Обновление {req.class_.name}: всего {total} (платно {paid}, бесплатно {free})"


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

# ===== НОВОЕ: интеграция с СКУД Sigur =====

def get_teacher_by_card_number(card_number: str, school_id: int) -> TeacherDTO | None:
    """Ищет активного учителя по номеру карты в указанной школе."""
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
    """Обновляет статус нахождения внутри школы."""
    with get_db() as db:
        t = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if t:
            t.is_inside = is_inside
            db.commit()