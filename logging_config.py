import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logging():
    # Создаем папку logs, если её нет
    os.makedirs("logs", exist_ok=True)

    # Настройка файлового логгера с ротацией (10 МБ на файл, 5 файлов)
    file_handler = RotatingFileHandler(
        "logs/bot.log", maxBytes=10*1024*1024, backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

    # Консольный вывод для отладки
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    root_logger.addHandler(console_handler)
