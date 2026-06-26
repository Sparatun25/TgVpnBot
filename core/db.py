"""Асинхронное подключение к базе данных.

Реализует:
1. Пулинг соединений с pre-ping (проверка живости коннекта перед запросом).
2. Slow-query logging: запросы дольше SLOW_QUERY_THRESHOLD_MS логируются с warning.
3. Мониторинг пула: подключение/отключение логируется на debug-уровне.
"""

import logging
import time

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import Pool

from core.config import settings
from core.metrics import db_slow_queries_total

logger = logging.getLogger(__name__)

# Порог «медленного» запроса. Выбираем 500 мс — типичный web-endpoint
# должен укладываться в это время. Если упираемся — повод искать медленный запрос.
SLOW_QUERY_THRESHOLD_MS = 500


engine = create_async_engine(
    settings.database_url,
    echo=False,
    # pool_size=10, max_overflow=5 на worker. При 4 uvicorn worker'ах
    # максимум 4 × 15 = 60 коннектов — комфортно ниже дефолтного
    # Postgres max_connections=100 (с запасом на миграции и psql-сессии).
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,  # проверяет соединение перед выдачей из пула
    pool_recycle=3600,   # пересоздаёт коннект каждый час (страховка от timeout)
)


async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ─────────────────────────────────────────────────────────
# Event-listener'ы для наблюдаемости
# ─────────────────────────────────────────────────────────

@event.listens_for(engine.sync_engine, "connect")
def receive_connect(dbapi_connection, connection_record):  # noqa: ARG001
    """Логируем новое соединение в пуле (debug — слишком шумно для info)."""
    logger.debug("Новое соединение с БД: %s", connection_record)


@event.listens_for(engine.sync_engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):  # noqa: ARG001
    """Логируем выдачу коннекта из пула (полезно для отладки утечек)."""
    logger.debug("Выдан коннект из пула: %s", connection_record)


@event.listens_for(Pool, "invalidate")
def receive_invalidate(dbapi_connection, connection_record, exception):  # noqa: ARG001
    """Логируем инвалидацию соединения (например, из-за pre-ping failure)."""
    logger.warning(
        "Соединение с БД инвалидировано: %s",
        exception or "без exception",
    )


# ─────────────────────────────────────────────────────────
# Slow-query logging: измеряем время выполнения каждого запроса.
# ─────────────────────────────────────────────────────────

@event.listens_for(engine.sync_engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
    """Ставим таймер перед выполнением запроса."""
    context._query_start_time = time.monotonic()


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
    """Считаем длительность и логируем warning для медленных запросов."""
    start = getattr(context, "_query_start_time", None)
    if start is None:
        return
    elapsed_ms = (time.monotonic() - start) * 1000
    if elapsed_ms >= SLOW_QUERY_THRESHOLD_MS:
        # Сокращаем statement до одной строки для читаемости лога.
        compact = " ".join(statement.split())
        logger.warning(
            "Slow query: %.0f ms — %s",
            elapsed_ms,
            compact[:300],
        )
        db_slow_queries_total.inc()


async def get_session() -> AsyncSession:
    """Получить сессию базы данных (для зависимости FastAPI)."""
    async with async_session_factory() as session:
        yield session
