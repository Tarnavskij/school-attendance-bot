# core/roles.py
from enum import StrEnum
from repositories import get_teacher_by_telegram_id
from config import ADMIN_TELEGRAM_ID


class Role(StrEnum):
    ADMIN = "admin"
    DIRECTOR = "director"
    CLASS_TEACHER = "class_teacher"
    SUBJECT_TEACHER = "subject_teacher"
    SECRETARY = "secretary"


ROLE_LABELS: dict[str, str] = {
    Role.ADMIN: "Администратор",
    Role.DIRECTOR: "Директор",
    Role.CLASS_TEACHER: "Классный руководитель",
    Role.SUBJECT_TEACHER: "Учитель-предметник",
    Role.SECRETARY: "Секретарь",
}

ALL_ROLES = list(ROLE_LABELS.keys())


def is_admin(user_id: int) -> bool:
    if user_id == ADMIN_TELEGRAM_ID:
        return True
    teacher = get_teacher_by_telegram_id(user_id)
    return teacher is not None and teacher.role == Role.ADMIN


def check_access(user_id: int, allowed_roles: list[str]) -> bool:
    if is_admin(user_id):
        return True
    teacher = get_teacher_by_telegram_id(user_id)
    return teacher is not None and teacher.role in allowed_roles