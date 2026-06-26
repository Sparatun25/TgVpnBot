"""Главный модуль Telegram-бота."""

import asyncio
import logging
import sys
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from prometheus_client import start_http_server

from core.config import settings
from core.logging import get_logger, setup_logging
from core.middleware import bind_request_id_for_update
from database.init_db import init_db, check_connection
from bot.handlers import start
from bot.services.scheduler import start_notification_scheduler

# Настройка логирования ДО любых других импортов, которые могут логировать.
# setup_logging() идемпотентен и подменяет root-логгер на structlog pipeline —
# все существующие `logging.getLogger(__name__)` будут идти через structlog
# (stdlib bridge). Поведение по умолчанию визуально неотличимо от прежнего.
setup_logging()
logger = get_logger(__name__)


class UpdateContextMiddleware(BaseMiddleware):
    """Биндит request_id + tg_id + chat_id в structlog contextvars на время Update.

    Без этого контекст из RequestIdMiddleware (HTTP) не виден в логах бота, и
    наоборот: каждый Telegram update стартует с чистого contextvars, что ломает
    сквозную трассировку. bind_contextvars в этом middleware автоматически
    подхватывается structlog merge_contextvars процессором.
    """

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        with bind_request_id_for_update(event):
            return await handler(event, data)


async def main() -> None:
    """Главная функция запуска бота."""
    logger.info("bot_starting")

    # Поднимаем Prometheus /metrics endpoint на отдельном порту.
    # Бот — отдельный процесс (не uvicorn worker), поэтому обычного
    # /metrics на 8000 нет — экспозим свой через daemon-поток.
    # Порт НЕ маппится наружу в docker-compose — Prometheus ходит через
    # Docker network (см. Phase 6: docker-compose.yml + Dockerfile.backend).
    start_http_server(settings.metrics_bot_port)
    logger.info("metrics_endpoint_started", port=settings.metrics_bot_port)

    # Проверяем подключение к БД и создаём таблицы
    if not await check_connection():
        logger.error("db_connection_failed")
        return
    await init_db()

    # Инициализация бота
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Инициализация диспетчера
    dp = Dispatcher(storage=MemoryStorage())

    # Биндим request_id/tg_id к contextvars для каждого Telegram Update.
    # dp.update.middleware() ловит ВСЕ типы updates (message, callback_query,
    # inline_query, ...). Регистрируем ПЕРВЫМ — до пользовательских middleware.
    dp.update.middleware(UpdateContextMiddleware())

    # Подключение роутеров
    dp.include_router(start.router)

    # Запуск планировщика уведомлений
    scheduler = await start_notification_scheduler(bot)

    logger.info("bot_started")

    try:
        # Запуск polling
        await dp.start_polling(bot)
    finally:
        # Остановка планировщика при завершении
        scheduler.shutdown()
        await bot.session.close()
        logger.info("bot_stopping")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logger.exception("Критическая ошибка: %s", e)
        sys.exit(1)
