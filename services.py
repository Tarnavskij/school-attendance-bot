# services.py
from datetime import date
from aiogram import Bot
from repositories import (
    get_teacher_by_telegram_id, get_available_classes, get_students_by_class,
    create_session, add_records, toggle_student_presence, finish_session,
    get_active_sessions, get_sessions_for_report, CreatedSession, SessionAlreadyExists,
    get_session_notification_data,
    get_class_teacher_for_class,
    mark_notify_sent,
    save_attendance_transactional,
    check_edit_deadline,
    try_acquire_editor_lock,
    release_editor_lock,
    close_partial_sessions as repo_close_partial_sessions,
    finalize_due_sessions as repo_finalize_due_sessions,
    LOCK_ACQUIRED,
    LOCK_ALREADY_OWNED,
    LOCK_BUSY,
    LOCK_CLOSED,
)
from config import ADMIN_TELEGRAM_ID


class AttendanceService:

    @staticmethod
    def start_attendance(telegram_id: int, class_id: int,
                         teacher_school_id: int):
        teacher = get_teacher_by_telegram_id(telegram_id)
        if not teacher:
            return None, "Вы не зарегистрированы. Обратитесь к администратору."

        # teacher_school_id теперь обязателен
        school_id = teacher_school_id

        if class_id not in {c.id for c in get_available_classes(date.today(), school_id=school_id, teacher_id=teacher.id)}:
            return None, "Этот класс уже занят или недоступен."

        try:
            session = create_session(teacher.id, class_id, school_id=school_id)
        except SessionAlreadyExists:
            return None, "Этот класс уже занят или недоступен."

        students = get_students_by_class(class_id, school_id=school_id)
        add_records(session.id, [s.id for s in students])
        return session, students

    @staticmethod
    def toggle_student(session_id: int, student_id: int) -> bool:
        return toggle_student_presence(session_id, student_id)

    @staticmethod
    def complete_session(session_id: int) -> None:
        finish_session(session_id, auto=False)

    @staticmethod
    async def submit_session(
        bot: Bot,
        session_id: int,
        teacher_id: int,
        all_records: list[tuple[int, bool, str | None]],
        changed_student_ids: list[int],
        mode: str,
        skip_deadline: bool = False,
    ) -> tuple[bool, str]:
        """
        Единая точка submit для переклички.

        mode:
          - "new_all"      — первый и единственный участник, весь класс
          - "new_partial"  — первый участник подгруппы
          - "partial_join" — второй участник (закрывает)

        Возвращает (True, "") или (False, причина).

        Побочные эффекты:
          - обновление БД через save_attendance_transactional
          - notify_web("summary_update") при успехе
          - notify_class_teacher при переходе в completed
        """
        # Целевой статус
        if mode in ("new_all", "partial_join"):
            target_status = "completed"
        elif mode == "new_partial":
            target_status = "partial"
        else:
            return False, "invalid_mode"

        ok, reason = save_attendance_transactional(
            session_id=session_id,
            teacher_id=teacher_id,
            all_records=all_records,
            changed_student_ids=changed_student_ids,
            target_status=target_status,
            mode=mode,
            skip_deadline=skip_deadline,
        )

        if not ok:
            return False, reason

        # SSE — веб-панель перерисует сводку
        notify = getattr(bot, "notify_web", None)
        if notify:
            await notify("summary_update")

        # Уведомление class_teacher — только для completed
        if target_status == "completed":
            await ReportService.notify_class_teacher(bot, session_id)

        return True, ""

    @staticmethod
    def join_partial(
        session_id: int,
        teacher_id: int,
    ) -> tuple[bool, str, dict | None]:
        """
        Учитель B хочет присоединиться к partial-сессии.

        Делает:
          1. Проверяет deadline (finalize_at).
          2. Пытается атомарно взять lock.

        Возвращает:
          (True, "", info)     — можно заходить
          (False, reason, None) — нельзя

        Возможные reason:
          - "deadline_expired"
          - "lock_busy"
          - "session_closed"
          - "session_not_found"
        """
        # 1. Deadline / статус
        ok, reason = check_edit_deadline(session_id)
        if not ok:
            return False, reason, None

        # 2. Lock
        lock_result = try_acquire_editor_lock(session_id, teacher_id)
        if lock_result == LOCK_CLOSED:
            return False, "session_not_found", None
        if lock_result == LOCK_BUSY:
            return False, "lock_busy", None
        # LOCK_ACQUIRED / LOCK_ALREADY_OWNED — ок, можно заходить

        return True, "", {"lock": lock_result}

    @staticmethod
    def cancel_join(session_id: int, teacher_id: int) -> None:
        """
        Отмена участия B: отпускаем lock, ничего не сохраняем.
        Сессия остаётся в статусе partial.
        """
        release_editor_lock(session_id, teacher_id)


class ReportService:

    @staticmethod
    async def finalize_day(bot: Bot) -> None:
        """
        Cron-джоб 20:00.

        Порядок (важно!):
          1. Закрыть все partial → completed (с уведомлениями).
          2. Закрыть все active → auto_completed (без уведомлений).
          3. Только после этого отправить административный отчёт.

        Если не сделать в таком порядке, отчёт будет построен по неполным
        данным (partial ещё висят).
        """
        from repositories import get_all_schools, get_active_sessions, finish_session

        # 1) partial → completed через общую логику
        await ReportService.close_partial_sessions(bot)

        # 2) active → auto_completed (без уведомления)
        schools = get_all_schools()
        for school in schools:
            for session in get_active_sessions(date.today(), school["id"]):
                finish_session(session.id, auto=True)

        # 3) административный отчёт — по свежим данным
        await ReportService.send_report(bot)

    @staticmethod
    async def send_report(bot: Bot) -> None:
        await bot.send_message(ADMIN_TELEGRAM_ID, ReportService.get_daily_summary(date.today()))

    @staticmethod
    async def notify_class_teacher(bot: Bot, session_id: int) -> None:
        """
        Отправляет class_teacher уведомление о закрытии переклички.

        Правила:
          - Если class_teacher не найден → считаем обязательство закрытым,
            помечаем notify_sent=True (не пытаемся слать бесконечно).
          - Если class_teacher сам участник сессии → не шлём,
            но помечаем notify_sent=True.
          - Если send_message упал → НЕ помечаем, повторная попытка
            произойдёт при следующем вызове scheduler'а (at-least-once).

        Возвращает None. Все ошибки логирует и глушит.
        """
        data = get_session_notification_data(session_id)
        if not data:
            # Сессии нет — нечего делать. Помечаем notify_sent, чтобы
            # scheduler не пытался снова.
            mark_notify_sent(session_id)
            return

        class_teacher = get_class_teacher_for_class(data["class_id"], data["school_id"])

        # Нет class_teacher — не шлём, но obligation закрыт
        if not class_teacher:
            mark_notify_sent(session_id)
            return

        # class_teacher сам участвовал — не шлём ему
        if class_teacher.id in data["participant_ids"]:
            mark_notify_sent(session_id)
            return

        # Собираем сообщение
        lines = [f"📋 Перекличка в вашем классе {data['class_name']} завершена."]

        if data["participant_names"]:
            lines.append(f"\nОтметили: {', '.join(data['participant_names'])}.")

        if data["absent"]:
            lines.append(f"\nОтсутствуют ({len(data['absent'])}):")
            for name, reason in data["absent"]:
                reason_str = f" — {reason}" if reason else ""
                lines.append(f"  • {name}{reason_str}")
        else:
            lines.append("\n✅ Все присутствовали")

        text = "\n".join(lines)

        # Отправляем. При ошибке — НЕ помечаем notify_sent,
        # scheduler попробует снова.
        try:
            await bot.send_message(class_teacher.telegram_id, text)
        except Exception:
            # Логировать — если есть logger, иначе просто пропускаем.
            # scheduler повторит попытку.
            return

        mark_notify_sent(session_id)

    @staticmethod
    async def close_partial_sessions(bot: Bot, school_id: int | None = None) -> int:
        """
        Cron-джоб 10:00.
        Все partial → completed. Для каждой — уведомление class_teacher.

        Возвращает количество закрытых сессий (для логов/отладки).
        """
        closed = repo_close_partial_sessions(school_id=school_id)

        for item in closed:
            await ReportService.notify_class_teacher(bot, item["session_id"])

        if closed:
            notify = getattr(bot, "notify_web", None)
            if notify:
                await notify("summary_update")

        return len(closed)

    @staticmethod
    async def finalize_due_sessions(bot: Bot, school_id: int | None = None) -> int:
        """
        Минутный cron-джоб.
        Закрывает сессии с истёкшим finalize_at, ретраит уведомления.

        Логика по статусу:
          - partial → completed : шлём уведомление
          - completed           : retry уведомления (не шлём, если notify_sent уже True)
          - active → auto_completed : НЕ шлём, но помечаем notify_sent=True,
                                       чтобы не крутиться вечно

        Возвращает количество обработанных сессий.
        """
        processed = repo_finalize_due_sessions(school_id=school_id)

        for item in processed:
            if item["status"] == "auto_completed":
                # Аварийный случай. Не уведомляем, но обязательство закрываем.
                mark_notify_sent(item["session_id"])
                continue

            # partial → completed или completed (retry) — уведомляем
            await ReportService.notify_class_teacher(bot, item["session_id"])

        if processed:
            notify = getattr(bot, "notify_web", None)
            if notify:
                await notify("summary_update")

        return len(processed)

    @staticmethod
    def get_daily_summary(target_date: date) -> str:
        # Для отчёта нужно передавать school_id. Чтобы не ломать логику,
        # будем получать все школы и объединять отчёты.
        from repositories import get_all_schools, get_sessions_for_report
        schools = get_all_schools()
        if not schools:
            return "Нет зарегистрированных школ."

        all_sessions = []
        for school in schools:
            all_sessions.extend(get_sessions_for_report(target_date, school["id"]))

        if not all_sessions:
            return "Сегодня перекличек не проводилось."

        class_summary: dict[str, dict] = {}
        for sess in all_sessions:
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