# config.py
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent / ".env")


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Обязательная переменная окружения не задана: {key}")
    return value


BOT_TOKEN: str = _require("BOT_TOKEN")
ADMIN_TELEGRAM_ID: int = int(_require("ADMIN_TELEGRAM_ID"))
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///school.db")
DEFAULT_SCHOOL_ID: int = 1
WEB_USERNAME: str = os.getenv("WEB_USERNAME", "admin")
WEB_PASSWORD: str = _require("WEB_PASSWORD")
FLASK_SECRET_KEY: str = _require("FLASK_SECRET_KEY")