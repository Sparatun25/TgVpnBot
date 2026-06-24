"""Инициализация базы данных: создание таблиц при первом запуске."""

import asyncio
import logging
import sys

from sqlalchemy import text

from core.db import engine
from database.models import Base

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """
    Создать все таблицы в PostgreSQL.

    Безопасно вызывать повторно: использует IF NOT EXISTS.
    Для production-миграций — Alembic.
    """
    logger.info("Инициализация базы данных...")

    async with engine.begin() as conn:
        # Создаём все таблицы из моделей
        await conn.run_sync(Base.metadata.create_all)

        # Проверяем, что таблицы созданы
        result = await conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN ('users', 'subscriptions', 'payments')
                """
            )
        )
        tables = [row[0] for row in result]

    logger.info("Созданы таблицы: %s", ", ".join(tables) if tables else "нет")


async def check_connection() -> bool:
    """
    Проверить подключение к базе данных.

    Returns:
        True если подключение успешно.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Подключение к БД успешно")
        return True
    except Exception as e:
        logger.error("Ошибка подключения к БД: %s", e)
        return False


async def main() -> None:
    """Точка входа для CLI-запуска."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Проверяем подключение
    if not await check_connection():
        logger.error("Не удалось подключиться к БД")
        sys.exit(1)

    # Создаём таблицы
    await init_db()

    logger.info("База данных готова к работе")

    # Закрываем движок
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
