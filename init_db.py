# init_db.py
from database import Base, engine, SessionLocal, School, Teacher, Class, Student
from config import ADMIN_TELEGRAM_ID

Base.metadata.create_all(bind=engine)

db = SessionLocal()

# Создаём школу
school = School(name="Основная школа")
db.add(school)
db.commit()

# Классы с grade и letter
classes_data = [
    ("5А", 5, "А"), ("5Б", 5, "Б"), ("5В", 5, "В"),
    ("6А", 6, "А"), ("6Б", 6, "Б"), ("6В", 6, "В"),
    ("7А", 7, "А"), ("7Б", 7, "Б"),
    ("8А", 8, "А"), ("8Б", 8, "Б"),
    ("9А", 9, "А"), ("9Б", 9, "Б"),
    ("10А", 10, "А"), ("10Б", 10, "Б"),
    ("11А", 11, "А"), ("11Б", 11, "Б"),
]
class_objs = []
for name, grade, letter in classes_data:
    cls = Class(name=name, grade=grade, letter=letter, school_id=school.id)
    db.add(cls)
    class_objs.append((name, cls))
db.commit()
# Словарь для быстрого доступа
class_map = {name: cls for name, cls in class_objs}

# Администратор
admin = Teacher(telegram_id=ADMIN_TELEGRAM_ID, name="Администратор", role="admin", school_id=school.id)
db.add(admin)
db.commit()

# Тестовые ученики
sample_students = {
    "5А": ["Иванов И.И.", "Петров П.П.", "Сидорова А.С."],
    "5Б": ["Козлов К.К.", "Морозова М.М."],
    "6А": ["Соколов С.С.", "Попова П.П."],
    "6Б": ["Гусев Г.Г.", "Фёдорова Ф.Ф."],
}
for class_name, names in sample_students.items():
    cls = class_map[class_name]
    db.add_all([Student(name=n, class_id=cls.id, school_id=school.id) for n in names])
db.commit()
db.close()

print("✅ База данных инициализирована с grade/letter и тестовыми классами.")