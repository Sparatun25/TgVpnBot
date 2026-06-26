"""Инициализация базы данных: применяет миграции Alembic.

Используется Alembic вместо Base.metadata.create_all, чтобы:
- фиксировать историю изменений схемы (migrations/versions/);
- безопасно накатывать обновления на прод без потери данных;
- делать downgrade в случае отката.

Подробнее: migrations/README.md.
"""

import asyncio
import logging
import sys

from sqlalchemy import inspect, text

from core.db import engine

logger = logging.getLogger(__name__)


def _run_alembic_upgrade() -> None:
    """Запустить `alembic upgrade head` синхронно из async-контекста.

    alembic CLI использует собственный argparse и блокирующий ввод/вывод,
    поэтому выполняем его через subprocess — это безопаснее, чем
    программный вызов Alembic API (тот плохо дружит с уже запущенным
    event loop приложения).
    """
    import subprocess

    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.error("alembic upgrade head failed:\n%s", result.stderr or result.stdout)
        raise RuntimeError(f"alembic upgrade head failed: {result.stderr or result.stdout}")
    if result.stdout:
        for line in result.stdout.strip().splitlines():
            logger.info("alembic: %s", line)


async def init_db() -> None:
    """Применить все миграции Alembic до head.

    Безопасно вызывать повторно: Alembic пропускает уже применённые
    миграции благодаря таблице alembic_version.
    """
    logger.info("Применение миграций Alembic (alembic upgrade head)...")
    await asyncio.to_thread(_run_alembic_upgrade)

    def _list_tables(sync_conn):
        inspector = inspect(sync_conn)
        return sorted(inspector.get_table_names())

    async with engine.connect() as conn:
        tables = await conn.run_sync(_list_tables)

    logger.info(
        "База готова. Таблицы: %s",
        ", ".join(tables) if tables else "нет",
    )


async def check_connection() -> bool:
    """Проверить подключение к базе данных.

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
    """Точка входа для CLI-запуска: `python -m database.init_db`."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if not await check_connection():
        logger.error("Не удалось подключиться к БД")
        sys.exit(1)

    await init_db()

    logger.info("База данных готова к работе")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
