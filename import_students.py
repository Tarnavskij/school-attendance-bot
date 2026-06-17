# import_students.py  —  импорт учеников из Excel
# Формат файла: колонка A — фамилия/имя, колонка B — название класса (напр. "5А")
import sys
from pathlib import Path
from openpyxl import load_workbook
from database import Base, engine, SessionLocal, Class, Student

Base.metadata.create_all(bind=engine)


def import_from_excel(file_path: str) -> None:
    wb = load_workbook(file_path)
    ws = wb.active
    db = SessionLocal()
    added = skipped = 0

    for row in ws.iter_rows(min_row=1, values_only=True):
        if not row or len(row) < 2 or not row[0] or not row[1]:
            continue
        name = str(row[0]).strip()
        class_name = str(row[1]).strip()

        class_obj = db.query(Class).filter(Class.name == class_name).first()
        if not class_obj:
            class_obj = Class(name=class_name)
            db.add(class_obj)
            db.commit()

        exists = db.query(Student).filter(
            Student.name == name,
            Student.class_id == class_obj.id,
        ).first()
        if exists:
            skipped += 1
            continue

        db.add(Student(name=name, class_id=class_obj.id))
        added += 1

    db.commit()
    db.close()
    print(f"✅ Готово. Добавлено: {added}, пропущено дубликатов: {skipped}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python import_students.py файл.xlsx")
        sys.exit(1)
    path = sys.argv[1]
    if not Path(path).exists():
        print(f"Файл не найден: {path}")
        sys.exit(1)
    import_from_excel(path)