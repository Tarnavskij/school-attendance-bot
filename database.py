# database.py
from sqlalchemy import (
    create_engine, Column, BigInteger, Integer, String,
    Boolean, DateTime, Date, ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, date
from config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=5,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    teachers = relationship("Teacher", back_populates="school")
    classes = relationship("Class", back_populates="school")
    students = relationship("Student", back_populates="school")
    attendance_sessions = relationship("AttendanceSession", back_populates="school")
    registration_requests = relationship("RegistrationRequest", back_populates="school")


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="subject_teacher")
    is_active = Column(Boolean, nullable=False, default=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="SET NULL"), nullable=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, default=1)

    class_ = relationship("Class", back_populates="teacher")
    school = relationship("School", back_populates="teachers")
    sessions = relationship(
        "AttendanceSession",
        back_populates="teacher",
        foreign_keys="AttendanceSession.teacher_id",
    )
    meal_requests = relationship("MealRequest", back_populates="submitted_by", cascade="all, delete-orphan")


class Class(Base):
    __tablename__ = "classes"
    __table_args__ = (
        UniqueConstraint("name", "school_id", name="uq_class_name_per_school"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    grade = Column(Integer, nullable=True)
    letter = Column(String(5), nullable=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, default=1)

    students = relationship("Student", back_populates="class_")
    sessions = relationship("AttendanceSession", back_populates="class_")
    teacher = relationship("Teacher", back_populates="class_", uselist=False)
    school = relationship("School", back_populates="classes")
    meal_requests = relationship("MealRequest", back_populates="class_", cascade="all, delete-orphan")


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, default=1)
    meal_type = Column(String(10), default="paid", nullable=False)  # "paid" или "free"

    class_ = relationship("Class", back_populates="students")
    school = relationship("School", back_populates="students")
    records = relationship("AttendanceRecord", back_populates="student", cascade="all, delete-orphan")
    meal_items = relationship("MealRequestItem", back_populates="student", cascade="all, delete-orphan")


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    __table_args__ = (
        UniqueConstraint(
            "class_id", "session_date", "school_id",
            name="uq_class_session_per_day_per_school",
        ),
        Index("ix_session_date_status", "session_date", "status"),
    )

    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    session_date = Column(Date, default=date.today, nullable=False)
    start_time = Column(DateTime, default=datetime.now, nullable=False)
    end_time = Column(DateTime, nullable=True)
    status = Column(String(20), default="active", nullable=False, index=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, default=1)

    teacher = relationship("Teacher", back_populates="sessions")
    class_ = relationship("Class", back_populates="sessions")
    school = relationship("School", back_populates="attendance_sessions")
    records = relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True)
    session_id = Column(
        Integer, ForeignKey("attendance_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    student_id = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    is_present = Column(Boolean, default=True, nullable=False)
    reason = Column(String(255), nullable=True)

    session = relationship("AttendanceSession", back_populates="records")
    student = relationship("Student", back_populates="records")


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"
    __table_args__ = (
        Index("ix_reg_req_telegram_school_status", "telegram_id", "school_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    class_name = Column(String(50), nullable=True)
    status = Column(String(20), default="pending", nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, default=1)

    school = relationship("School", back_populates="registration_requests")


# ===== Новые таблицы: питание =====

class MealRequest(Base):
    __tablename__ = "meal_requests"
    __table_args__ = (
        UniqueConstraint("class_id", "request_date", "school_id", name="uq_meal_class_date_school"),
    )

    id = Column(Integer, primary_key=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    request_date = Column(Date, default=date.today, nullable=False)
    submitted_by_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, default=1)
    submitted_at = Column(DateTime, default=datetime.now, nullable=False)

    class_ = relationship("Class", back_populates="meal_requests")
    submitted_by = relationship("Teacher", back_populates="meal_requests")
    items = relationship("MealRequestItem", back_populates="request", cascade="all, delete-orphan")


class MealRequestItem(Base):
    __tablename__ = "meal_request_items"

    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("meal_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    is_eating = Column(Boolean, default=True, nullable=False)
    meal_type = Column(String(10), default="paid", nullable=False)  # "paid" или "free"

    request = relationship("MealRequest", back_populates="items")
    student = relationship("Student", back_populates="meal_items")