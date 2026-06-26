"""Alembic environment с поддержкой async SQLAlchemy.

Особенности:
1. DATABASE_URL берётся из core.config.settings (pydantic-settings), а не из env.
   Это единая точка истины для всего приложения — и бэкенд, и миграции
   подключаются к одной и той же БД с одними и теми же credentials.
2. Async-движок: проект использует SQLAlchemy 2.x async (asyncpg для PG,
   aiosqlite для SQLite). Alembic должен работать в том же режиме.
3. target_metadata = Base.metadata — autogenerate сравнивает с этим metadata.
4. Поддерживаемые схемы: postgresql+asyncpg (прод) и sqlite+aiosqlite (dev/E2E).
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Добавляем корень проекта в sys.path, чтобы `from core.config import settings`
# работал и при запуске `alembic` из любой директории.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import settings  # noqa: E402
from database.models import Base  # noqa: E402

# Этот объект — то, с чем Alembic сравнивает состояние БД при autogenerate.
config = context.config

# Подменяем sqlalchemy.url на URL из settings. В alembic.ini эта переменная
# пустая, иначе пришлось бы дублировать URL в env (нарушение DRY).
config.set_main_option("sqlalchemy.url", settings.database_url)

# Настройка логирования из alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Запуск миграций в offline-режиме (генерация SQL без подключения к БД).

    Используется, когда нужно сгенерировать SQL-скрипт для ручного применения
    DBA, который не даёт приложению прямого доступа к БД:
        alembic upgrade head --sql > migration.sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Запуск миграций в online-режиме (sync-callback внутри async-контекста).

    Alembic исторически sync, поэтому запускается через connection.run_sync.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # include_schemas=True нужен, если используются не-default схемы PG.
        # У нас одна public — поэтому не включаем.
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Async online-режим: создаём async engine и запускаем миграции."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Запуск миграций в online-режиме.

    Определяем, async или sync URL: project использует postgresql+asyncpg
    и sqlite+aiosqlite (только async). Если в будущем добавим sync-драйвер —
    здесь будет ветка.
    """
    url = config.get_main_option("sqlalchemy.url") or ""
    if url.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite://")):
        asyncio.run(run_async_migrations())
    else:
        # Запасной sync-путь (psycopg2 / pysqlite) — в текущем проекте
        # не используется, но пусть будет для совместимости со стандартным
        # шаблоном Alembic.
        from sqlalchemy import engine_from_config

        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            do_run_migrations(connection)

        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
