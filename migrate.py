# migrate.py
"""
Скрипт для безопасного добавления новых колонок в таблицу teachers.
Запускать один раз на сервере после обновления кода.
"""
from database import engine
from sqlalchemy import text, inspect


def run_migration():
    with engine.connect() as conn:
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('teachers')]

        if 'card_number' not in columns:
            conn.execute(text("ALTER TABLE teachers ADD COLUMN card_number VARCHAR(50)"))
            print("✅ Добавлена колонка card_number")
        else:
            print("ℹ️ Колонка card_number уже существует")

        if 'is_inside' not in columns:
            conn.execute(text("ALTER TABLE teachers ADD COLUMN is_inside BOOLEAN DEFAULT FALSE NOT NULL"))
            print("✅ Добавлена колонка is_inside")
        else:
            print("ℹ️ Колонка is_inside уже существует")

        # Создаём индекс (для PostgreSQL)
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_teachers_card_number ON teachers(card_number)"))
            print("✅ Индекс idx_teachers_card_number создан (или уже существовал)")
        except Exception as e:
            print(f"⚠️ Индекс не был создан: {e}")

        conn.commit()
        print("✅ Миграция завершена")


if __name__ == "__main__":
    run_migration()