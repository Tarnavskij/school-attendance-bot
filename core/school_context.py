# core/school_context.py
"""
Контекст текущей школы — привязан к telegram_id администратора.
"""
from config import DEFAULT_SCHOOL_ID

_admin_school_map: dict[int, int] = {}

def get_school_id_for_admin(telegram_id: int) -> int:
    """Возвращает ID активной школы для данного администратора."""
    return _admin_school_map.get(telegram_id, DEFAULT_SCHOOL_ID)

def set_school_id_for_admin(telegram_id: int, school_id: int) -> None:
    """Устанавливает ID активной школы для данного администратора."""
    _admin_school_map[telegram_id] = school_id