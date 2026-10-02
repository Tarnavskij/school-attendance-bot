import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch
from database import Base
import repositories


@pytest.fixture(scope="function")
def test_db():
    """
    Фикстура, создающая временную SQLite БД и подменяющая SessionLocal в repositories.

    После yield отдаёт объект-сессию, привязанный к тестовой БД.
    Все репозиторные функции, использующие repositories.SessionLocal,
    увидят тестовую БД, пока фикстура активна.
    """
    test_engine = create_engine(
        "sqlite:///:memory:?cache=shared",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(test_engine)
    TestSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    with patch("repositories.SessionLocal", TestSessionLocal):
        # Создаём школу в тестовой БД
        db = TestSessionLocal()
        from database import School
        school = School(name="Test School")
        db.add(school)
        db.commit()
        db.close()

        yield TestSessionLocal()

    Base.metadata.drop_all(test_engine)