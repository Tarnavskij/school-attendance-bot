import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch
from database import Base
import repositories

@pytest.fixture(scope="function")
def test_db():
    """Фикстура, создающая временную SQLite БД и подменяющая SessionLocal в repositories."""
    # Создаём тестовый engine
    test_engine = create_engine(
        "sqlite:///:memory:?cache=shared",
        echo=False,
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(test_engine)
    TestSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    # Патчим repositories.SessionLocal на тестовый
    with patch('repositories.SessionLocal', TestSessionLocal):
        # Создаём школу в тестовой БД
        db = TestSessionLocal()
        from database import School
        school = School(name="Test School")
        db.add(school)
        db.commit()
        school_id = school.id
        db.close()

        # Подмена get_current_school_id
        def fake_get_current_school_id():
            return school_id
        original_get = repositories.get_current_school_id
        repositories.get_current_school_id = fake_get_current_school_id

        yield TestSessionLocal()

        # Восстанавливаем оригинальный get_current_school_id
        repositories.get_current_school_id = original_get

    Base.metadata.drop_all(test_engine)