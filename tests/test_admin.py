import pytest
from database import SessionLocal, Teacher
from ensure_admin import ensure_admin
from config import ADMIN_TELEGRAM_ID

def test_ensure_admin_creates_if_missing():
    db = SessionLocal()
    # Удаляем админа, если есть
    db.query(Teacher).filter(Teacher.telegram_id == ADMIN_TELEGRAM_ID).delete()
    db.commit()
    db.close()

    ensure_admin()

    db = SessionLocal()
    admin = db.query(Teacher).filter(Teacher.telegram_id == ADMIN_TELEGRAM_ID).first()
    db.close()
    assert admin is not None
    assert admin.role == "admin"
    assert admin.is_active == True