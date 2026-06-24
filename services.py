# services.py
from datetime import date
from aiogram import Bot
from repositories import (
    get_teacher_by_telegram_id, get_available_classes, get_students_by_class,
    create_session, add_records, toggle_student_presence, finish_session,
    get_active_sessions, get_sessions_for_report, CreatedSession, SessionAlreadyExists,
    delete_session as repo_delete_session, get_db as repo_get_db,
)
from config import ADMIN_TELEGRAM_ID
from core.school_context import get_current_school_id


class AttendanceService:

    @staticmethod
    def start_attendance(telegram_id: int, class_id: int, is_admin_user: bool = False):
        teacher = get_teacher_by_telegram_id(telegram_id)
        if not teacher:
            return None, "Вы не зарегистрированы. Обратитесь к администратору."

        # Для обычного учителя проверяем, что класс свободен
        if not is_admin_user and class_id not in {c.id for c in get_available_classes(date.today())}:
            return None, "Этот класс уже занят или недоступен."

        # Администратор может перезаписывать существующую сессию
        if is_admin_user:
            from database import AttendanceSession
            with repo_get_db() as db:
                old = db.query(AttendanceSession).filter(
                    AttendanceSession.class_id == class_id,
                    AttendanceSession.session_date == date.today(),
                    AttendanceSession.school_id == get_current_school_id(),
                ).first()
                if old:
                    db.delete(old)
                    db.flush()

        try:
            session = create_session(teacher.id, class_id)
        except SessionAlreadyExists:
            return None, "Этот класс уже занят или недоступен."

        students = get_students_by_class(class_id)
        add_records(session.id, [s.id for s in students])
        return session, students

    @staticmethod
    def toggle_student(session_id: int, student_id: int) -> bool:
        return toggle_student_presence(session_id, student_id)

    @staticmethod
    def complete_session(session_id: int) -> None:
        finish_session(session_id, auto=False)


class ReportService:

    @staticmethod
    async def finalize_day(bot: Bot) -> None:
        for session in get_active_sessions(date.today()):
            finish_session(session.id, auto=True)
        await ReportService.send_report(bot)

    @staticmethod
    async def send_report(bot: Bot) -> None:
        await bot.send_message(ADMIN_TELEGRAM_ID, ReportService.get_daily_summary(date.today()))

    @staticmethod
    def get_daily_summary(target_date: date) -> str:
        sessions = get_sessions_for_report(target_date)
        if not sessions:
            return "Сегодня перекличек не проводилось."
        class_summary: dict[str, dict] = {}
        for sess in sessions:
            if sess.class_name not in class_summary:
                class_summary[sess.class_name] = {"teacher": sess.teacher_name, "absent": set()}
            class_summary[sess.class_name]["absent"].update(name for name, _ in sess.absent)
        lines = [f"📅 Сводка за {target_date.strftime('%d.%m.%Y')}:"]
        for class_name, info in sorted(class_summary.items()):
            absent_list = sorted(info["absent"])
            if absent_list:
                lines.append(f"🔹 {class_name} (отмечал {info['teacher']}):")
                lines.extend(f"   • {name}" for name in absent_list)
            else:
                lines.append(f"🔹 {class_name}: отсутствующих нет")
        return "\n".join(lines)