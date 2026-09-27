# migrate.py
"""
Скрипт для безопасного добавления новых колонок в таблицы.
Запускать после обновления кода (идемпотентно — можно сколько угодно раз).
"""
from datetime import datetime, timedelta
from sqlalchemy import text, inspect
from database import engine
from config import EDIT_WINDOW_MINUTES


def _column_exists(inspector, table: str, column: str) -> bool:
    """Проверяет, есть ли колонка в таблице."""
    cols = [c["name"] for c in inspector.get_columns(table)]
    return column in cols


def run_migration():
    dialect = engine.dialect.name
    # Типы, зависящие от СУБД (для ALTER ... ADD COLUMN)
    DT_TYPE = "TIMESTAMP" if dialect == "postgresql" else "DATETIME"
    BOOL_TYPE = "BOOLEAN"  # OK и в SQLite, и в PostgreSQL
    TEXT_TYPE = "TEXT"     # JSON в SQLite = TEXT, в PostgreSQL тоже валидно

    with engine.connect() as conn:
        inspector = inspect(engine)

        # ── 1. Старые миграции (таблица teachers) ───────────────────────────
        if not _column_exists(inspector, "teachers", "card_number"):
            conn.execute(text("ALTER TABLE teachers ADD COLUMN card_number VARCHAR(50)"))
            print("✅ teachers.card_number добавлена")
        else:
            print("ℹ️ teachers.card_number уже существует")

        if not _column_exists(inspector, "teachers", "is_inside"):
            conn.execute(text(f"ALTER TABLE teachers ADD COLUMN is_inside {BOOL_TYPE} DEFAULT FALSE NOT NULL"))
            print("✅ teachers.is_inside добавлена")
        else:
            print("ℹ️ teachers.is_inside уже существует")

        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_teachers_card_number ON teachers(card_number)"))
        except Exception as e:
            print(f"⚠️ Индекс idx_teachers_card_number: {e}")

        # ── 2. Multi-teacher: attendance_sessions ────────────────────────────
        if not _column_exists(inspector, "attendance_sessions", "editor_teacher_id"):
            conn.execute(text("ALTER TABLE attendance_sessions ADD COLUMN editor_teacher_id INTEGER"))
            print("✅ attendance_sessions.editor_teacher_id добавлена")
        else:
            print("ℹ️ attendance_sessions.editor_teacher_id уже существует")

        if not _column_exists(inspector, "attendance_sessions", "editor_locked_at"):
            conn.execute(text(f"ALTER TABLE attendance_sessions ADD COLUMN editor_locked_at {DT_TYPE}"))
            print("✅ attendance_sessions.editor_locked_at добавлена")
        else:
            print("ℹ️ attendance_sessions.editor_locked_at уже существует")

        if not _column_exists(inspector, "attendance_sessions", "participant_ids"):
            conn.execute(text(f"ALTER TABLE attendance_sessions ADD COLUMN participant_ids {TEXT_TYPE}"))
            print("✅ attendance_sessions.participant_ids добавлена")
        else:
            print("ℹ️ attendance_sessions.participant_ids уже существует")

        if not _column_exists(inspector, "attendance_sessions", "finalize_at"):
            conn.execute(text(f"ALTER TABLE attendance_sessions ADD COLUMN finalize_at {DT_TYPE}"))
            print("✅ attendance_sessions.finalize_at добавлена")
        else:
            print("ℹ️ attendance_sessions.finalize_at уже существует")

        if not _column_exists(inspector, "attendance_sessions", "notify_sent"):
            conn.execute(text(f"ALTER TABLE attendance_sessions ADD COLUMN notify_sent {BOOL_TYPE} DEFAULT FALSE NOT NULL"))
            print("✅ attendance_sessions.notify_sent добавлена")
        else:
            print("ℹ️ attendance_sessions.notify_sent уже существует")

        # ── 3. Multi-teacher: attendance_records ────────────────────────────
        if not _column_exists(inspector, "attendance_records", "marked_by_teacher_id"):
            conn.execute(text("ALTER TABLE attendance_records ADD COLUMN marked_by_teacher_id INTEGER"))
            print("✅ attendance_records.marked_by_teacher_id добавлена")
        else:
            print("ℹ️ attendance_records.marked_by_teacher_id уже существует")

        # ── 4. Backfill ──────────────────────────────────────────────────────
        # 4.1. Все уже завершённые сессии — notify_sent = TRUE,
        #      чтобы после деплоя им не слались уведомления повторно.
        conn.execute(text(
            "UPDATE attendance_sessions "
            "SET notify_sent = TRUE "
            "WHERE status IN ('completed', 'auto_completed') AND notify_sent = FALSE"
        ))
        print("✅ Backfill: notify_sent=True для завершённых сессий")

        # 4.2. У completed-сессий, где finalize_at ещё NULL и есть end_time,
        #      выставляем finalize_at = end_time + 45 минут.
        #      Делаем в Python (переносимо между SQLite и PostgreSQL).
        rows = conn.execute(text(
            "SELECT id, end_time FROM attendance_sessions "
            "WHERE status = 'completed' AND finalize_at IS NULL AND end_time IS NOT NULL"
        )).fetchall()

        updated = 0
        for row in rows:
            session_id, end_time = row[0], row[1]
            # SQLite возвращает строку, PostgreSQL — datetime.
            if isinstance(end_time, str):
                try:
                    end_time = datetime.fromisoformat(end_time)
                except ValueError:
                    continue
            new_finalize = end_time + timedelta(minutes=EDIT_WINDOW_MINUTES)
            conn.execute(
                text("UPDATE attendance_sessions SET finalize_at = :fa WHERE id = :sid"),
                {"fa": new_finalize, "sid": session_id},
            )
            updated += 1
        if updated:
            print(f"✅ Backfill: finalize_at для {updated} сессий")
        else:
            print("ℹ️ Backfill: finalize_at нечего заполнять")

        conn.commit()
        print("✅ Миграция завершена")


if __name__ == "__main__":
    run_migration()