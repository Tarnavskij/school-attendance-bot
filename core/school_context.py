# core/school_context.py
"""
Контекст текущей школы — привязан к telegram_id администратора.

Вместо глобальной переменной используем словарь {telegram_id: school_id},
чтобы два администратора могли независимо переключать школу.
Для веб-панели контекст по-прежнему хранится в flask.session.
"""
from config import DEFAULT_SCHOOL_ID

_admin_school_map: dict[int, int] = {}


def get_school_id_for_admin(telegram_id: int) -> int:
    """Возвращает ID активной школы для данного администратора."""
    return _admin_school_map.get(telegram_id, DEFAULT_SCHOOL_ID)


def set_school_id_for_admin(telegram_id: int, school_id: int) -> None:
    """Устанавливает ID активной школы для данного администратора."""
    _admin_school_map[telegram_id] = school_id


# ── Совместимость: «текущий» контекст для кода, вызываемого без telegram_id ──
# Используется только в репозитории как fallback; предпочитайте явный параметр.
_current_school_id: int = DEFAULT_SCHOOL_ID


def get_current_school_id() -> int:
    return _current_school_id


def set_current_school_id(school_id: int) -> None:
    global _current_school_id
    _current_school_id = school_id


def get_current_school_name() -> str | None:
    from repositories import get_all_schools
    for s in get_all_schools():
        if s["id"] == _current_school_id:
            return s["name"]
    return None