# reset_db.py
from database import Base, engine

def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("✅ База данных полностью очищена (все таблицы пересозданы пустыми).")

if __name__ == "__main__":
    reset_database()