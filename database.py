# database.py
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Date, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, date
from config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="subject_teacher")
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=True)

    class_ = relationship("Class", back_populates="teacher")
    sessions = relationship("AttendanceSession", back_populates="teacher")


class Class(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)

    students = relationship("Student", back_populates="class_")
    sessions = relationship("AttendanceSession", back_populates="class_")
    teacher = relationship("Teacher", back_populates="class_", uselist=False)


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False, index=True)

    class_ = relationship("Class", back_populates="students")
    records = relationship("AttendanceRecord", back_populates="student")


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    __table_args__ = (
        # Защита от гонки на уровне БД: один класс может иметь не более одной
        # сессии переклички в день, независимо от статуса (active/completed/auto_completed).
        # Если два учителя почти одновременно создадут сессию для одного класса,
        # второй INSERT упадёт с IntegrityError — это ожидаемо и обрабатывается в repositories.create_session.
        UniqueConstraint("class_id", "session_date", name="uq_class_session_per_day"),
        Index("ix_session_date_status", "session_date", "status"),
    )

    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    # Чистая календарная дата сессии (без времени) — используется для всех фильтров
    # "перекличка за такой-то день" вместо func.date(start_time), что не дружит с индексами.
    session_date = Column(Date, default=date.today, nullable=False)
    start_time = Column(DateTime, default=datetime.now, nullable=False)
    end_time = Column(DateTime, nullable=True)
    status = Column(String(20), default="active", nullable=False, index=True)

    teacher = relationship("Teacher", back_populates="sessions")
    class_ = relationship("Class", back_populates="sessions")
    records = relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("attendance_sessions.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    is_present = Column(Boolean, default=True, nullable=False)
    reason = Column(String(255), nullable=True)

    session = relationship("AttendanceSession", back_populates="records")
    student = relationship("Student", back_populates="records")

class RegistrationRequest(Base):
    __tablename__ = "registration_requests"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    class_name = Column(String(50), nullable=True)
    status = Column(String(20), default="pending", nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)