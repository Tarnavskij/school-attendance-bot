from database import SessionLocal, Teacher
from config import ADMIN_TELEGRAM_ID
from repositories import get_default_school_id

def ensure_admin():
    db = SessionLocal()
    try:
        admin = db.query(Teacher).filter(
            Teacher.telegram_id == ADMIN_TELEGRAM_ID,
            Teacher.role == "admin"
        ).first()
        if not admin:
            admin = Teacher(
                telegram_id=ADMIN_TELEGRAM_ID,
                name="Администратор",
                role="admin",
                school_id=get_default_school_id(),  # автоматически получает ID первой школы
                is_active=True
            )
            db.add(admin)
            db.commit()
            print(f"✅ Администратор создан (telegram_id={ADMIN_TELEGRAM_ID})")
        else:
            print("✅ Администратор уже существует")
    finally:
        db.close()