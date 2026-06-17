# bot.py
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN
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


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Router order matters: more specific routers first
    dp.include_router(registration_router)
    dp.include_router(admin_router)
    dp.include_router(director_router)
    dp.include_router(attendance_router)
    dp.include_router(my_class_router)
    dp.include_router(secretary_router)
    dp.include_router(common_router)

    # Scheduler — pass bot instance so ReportService doesn't need to create one
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