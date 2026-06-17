# init_db.py  —  запустить один раз для первоначального наполнения БД
from database import Base, engine, SessionLocal, Teacher, Class, Student
from config import ADMIN_TELEGRAM_ID

# Создаём все таблицы
Base.metadata.create_all(bind=engine)

db = SessionLocal()

# ── Классы ────────────────────────────────────────────────────────────────────
classes = [Class(name=n) for n in ("5А", "5Б", "6А", "6Б")]
db.add_all(classes)
db.commit()
class_map = {c.name: c.id for c in db.query(Class).all()}

# ── Администратор ─────────────────────────────────────────────────────────────
admin = Teacher(telegram_id=ADMIN_TELEGRAM_ID, name="Администратор", role="admin")
db.add(admin)
db.commit()

# ── Тестовые ученики (удали или замени своими) ────────────────────────────────
sample_students = {
    "5А": ["Иванов И.И.", "Петров П.П.", "Сидорова А.С."],
    "5Б": ["Козлов К.К.", "Морозова М.М."],
    "6А": ["Соколов С.С.", "Попова П.П."],
    "6Б": ["Гусев Г.Г.", "Фёдорова Ф.Ф."],
}
for class_name, names in sample_students.items():
    cid = class_map[class_name]
    db.add_all([Student(name=n, class_id=cid) for n in names])
db.commit()
db.close()

print("✅ База данных инициализирована.")