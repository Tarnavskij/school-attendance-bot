# helpers/session_card.py
"""
Утилита для получения карточки сегодняшней переклички учителя.
Используется в handlers/attendance.py и handlers/common.py.
"""
from datetime import date
from repositories import get_teacher_by_telegram_id, get_teacher_session_today


def get_today_session_card(telegram_id: int) -> str | None:
    """
    Возвращает текст карточки переклички, проведённой сегодня этим учителем.
    Если переклички не было — возвращает None.
    """
    teacher = get_teacher_by_telegram_id(telegram_id)
    if not teacher:
        return None

    session = get_teacher_session_today(teacher.id, date.today(), school_id=teacher.school_id)
    if not session:
        return None

    lines = [f"📋 Ваша перекличка сегодня — класс {session.class_name}"]
    if session.absent:
        lines.append(f"\nОтсутствуют ({len(session.absent)}):")
        for name, reason in session.absent:
            reason_str = f" — {reason}" if reason else ""
            lines.append(f"  • {name}{reason_str}")
    else:
        lines.append("\n✅ Все присутствовали")

    return "\n".join(lines)