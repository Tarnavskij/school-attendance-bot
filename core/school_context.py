# core/school_context.py
"""
Контекст текущей школы для администратора.

Пока реализован через глобальную переменную, так как подразумевается,
что администратор один. При необходимости масштабирования замените
на хранение в FSM-состоянии или в базе данных.
"""

from config import DEFAULT_SCHOOL_ID

_current_school_id: int = DEFAULT_SCHOOL_ID


def get_current_school_id() -> int:
    """Возвращает ID активной школы (для всех операций чтения/записи)."""
    return _current_school_id


def set_current_school_id(school_id: int) -> None:
    """Устанавливает ID активной школы."""
    global _current_school_id
    _current_school_id = school_id


def get_current_school_name() -> str | None:
    """Возвращает название текущей школы или None, если не найдено."""
    from repositories import get_all_schools
    for s in get_all_schools():
        if s['id'] == _current_school_id:
            return s['name']
    return None