# services.py
from datetime import date
from aiogram import Bot
from repositories import (
    get_teacher_by_telegram_id, get_available_classes, get_students_by_class,
    create_session, add_records, toggle_student_presence, finish_session,
    get_active_sessions, get_sessions_for_report, CreatedSession, SessionAlreadyExists,
)
from config import ADMIN_TELEGRAM_ID


class AttendanceService:

    @staticmethod
    def start_attendance(telegram_id: int, class_id: int):
        teacher = get_teacher_by_telegram_id(telegram_id)
        if not teacher:
            return None, "Вы не зарегистрированы. Обратитесь к администратору."
        if class_id not in {c.id for c in get_available_classes(date.today())}:
            return None, "Этот класс уже занят или недоступен."
        try:
            session = create_session(teacher.id, class_id)
        except SessionAlreadyExists:
            # Гонка: кто-то успел создать сессию для этого класса между проверкой
            # get_available_classes и нашим INSERT. Сообщение то же самое,
            # что и при обычной недоступности — пользователю не нужно знать детали.
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