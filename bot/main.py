"""Главный модуль Telegram-бота."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from core.config import settings
from database.init_db import init_db, check_connection
from bot.handlers import start
from bot.services.scheduler import start_notification_scheduler

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


async def main() -> None:
    """Главная функция запуска бота."""
    logger.info("Запуск OnyxVpn Telegram-бота...")

    # Проверяем подключение к БД и создаём таблицы
    if not await check_connection():
        logger.error("Не удалось подключиться к базе данных")
        return
    await init_db()

    # Инициализация бота
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Инициализация диспетчера
    dp = Dispatcher(storage=MemoryStorage())

    # Подключение роутеров
    dp.include_router(start.router)

    # Запуск планировщика уведомлений
    scheduler = await start_notification_scheduler(bot)

    logger.info("Бот успешно запущен")

    try:
        # Запуск polling
        await dp.start_polling(bot)
    finally:
        # Остановка планировщика при завершении
        scheduler.shutdown()
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logger.exception("Критическая ошибка: %s", e)
        sys.exit(1)
