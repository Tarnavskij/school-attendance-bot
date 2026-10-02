# helpers/session_card.py
"""
Утилита для получения карточки сегодняшней переклички учителя.
Используется в handlers/attendance.py.
"""
from datetime import date, datetime
from repositories import get_teacher_by_telegram_id, get_teacher_session_today


def get_today_session_card_data(telegram_id: int) -> dict | None:
    """
    Возвращает данные карточки переклички, проведённой сегодня этим учителем:
        {
          "text": str,
          "session_id": int,
          "status": str,            # active | partial | completed | auto_completed
          "can_edit": bool,         # показывать ли кнопку «Исправить»
          "finalize_at": datetime | None,
          "participant_names": list[str],
        }
    Или None, если переклички не было / учитель не участвовал.
    """
    teacher = get_teacher_by_telegram_id(telegram_id)
    if not teacher:
        return None

    session = get_teacher_session_today(teacher.id, date.today(), school_id=teacher.school_id)
    if not session:
        return None

    # ── Текст карточки ───────────────────────────────────────────────────────
    if session.status == "partial":
        lines = [f"📋 Ваша перекличка сегодня — класс {session.class_name} (частично)"]
    else:
        lines = [f"📋 Ваша перекличка сегодня — класс {session.class_name}"]

    if session.absent:
        lines.append(f"\nОтсутствуют ({len(session.absent)}):")
        for name, reason in session.absent:
            reason_str = f" — {reason}" if reason else ""
            lines.append(f"  • {name}{reason_str}")
    else:
        lines.append("\n✅ Все присутствовали")

    text = "\n".join(lines)

    # ── can_edit ─────────────────────────────────────────────────────────────
    can_edit = False
    now = datetime.now()

    if session.status == "completed":
        # Редактируем до finalize_at
        if session.finalize_at is None or now < session.finalize_at:
            can_edit = True

    elif session.status == "partial":
        # Редактируем только если мы participant (учитель, отправивший свою часть)
        # и deadline не истёк
        if session.participant_ids and teacher.id in session.participant_ids:
            if session.finalize_at is None or now < session.finalize_at:
                can_edit = True

    # auto_completed / active → can_edit = False

    return {
        "text": text,
        "session_id": session.id,
        "status": session.status,
        "can_edit": can_edit,
        "finalize_at": session.finalize_at,
        "participant_names": session.participant_names or [],
    }