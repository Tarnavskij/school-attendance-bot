# bot.py
import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, SSE_PUBLISH_TOKEN
from services import ReportService
from handlers.common import common_router
from handlers.registration import registration_router
from handlers.admin import admin_router
from handlers.director import director_router
from handlers.attendance import attendance_router
from handlers.my_class import my_class_router
from handlers.secretary import secretary_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

WEB_INTERNAL_URL = "http://127.0.0.1:5001/_publish"


async def notify_web_panel(event: str, data: dict | None = None) -> None:
    """Отправляет событие в веб-панель (SSE)."""
    try:
        async with aiohttp.ClientSession() as sess:
            await sess.post(
                WEB_INTERNAL_URL,
                json={"event": event, "data": data or {}},
                headers={"X-SSE-Token": SSE_PUBLISH_TOKEN},
                timeout=aiohttp.ClientTimeout(total=2),
            )
    except Exception as e:
        logger.warning(f"Не удалось уведомить веб-панель: {e}")


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(registration_router)
    dp.include_router(admin_router)
    dp.include_router(director_router)
    dp.include_router(attendance_router)
    dp.include_router(my_class_router)
    dp.include_router(secretary_router)
    dp.include_router(common_router)

    # Кладём функцию уведомления прямо в объект бота
    bot.notify_web = notify_web_panel  # динамически добавляем атрибут

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        ReportService.finalize_day,
        "cron",
        hour=20,
        minute=0,
        kwargs={"bot": bot},
        misfire_grace_time=60,
    )
    scheduler.start()
    logger.info("Scheduler started.")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())