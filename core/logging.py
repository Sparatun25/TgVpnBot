"""Централизованная настройка структурированного логирования (structlog + stdlib bridge).

Зачем: в проекте десятки модулей используют `logger = logging.getLogger(__name__)` —
это стандартный stdlib-паттерн. Чтобы не переписывать их все на structlog, мы
используем structlog.stdlib.ProcessorFormatter, который:

1. Перехватывает логи от ВСЕХ stdlib-логгеров (включая uvicorn, aiogram, sqlalchemy).
2. Прогоняет их через foreign_pre_chain процессоры (добавляют timestamp,
   contextvars, имя логгера, уровень).
3. Рендерит в JSON (прод) или цветной console (dev) через финальный процессор.

Contextvars (`request_id`, `tg_id`, `chat_id`, etc.) автоматически добавляются
в каждый лог через structlog.contextvars.merge_contextvars — это работает и для
structlog-логгеров, и для stdlib-логгеров.

Конфигурация управляется двумя env vars в core.config.Settings:
- LOG_LEVEL: DEBUG/INFO/WARNING/ERROR (default INFO)
- LOG_FORMAT: json/console (default console для удобства локальной разработки)

Обратная совместимость: если setup_logging() не вызван — приложение использует
basicConfig как раньше. Поведение по умолчанию (LOG_FORMAT=console, LOG_LEVEL=INFO)
визуально близко к старому формату.
"""

import logging
import sys

import structlog

from core.config import settings


def setup_logging() -> None:
    """Настроить structlog + stdlib logging.

    Безопасно вызывать несколько раз (idempotent): очищает handlers root logger'а.
    Должна быть вызвана из каждой точки входа (api/main.py, bot/main.py)
    ПЕРЕД первым импортом модулей, которые пишут в лог.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log_format = settings.log_format.lower()

    # Процессоры, общие для structlog-pipeline и для stdlib-foreign-логгеров.
    # Все они работают с event_dict (structlog) или с LogRecord.__dict__ (stdlib).
    shared_processors: list = [
        # Критично: добавляет contextvars (request_id, tg_id, ...) в КАЖДЫЙ лог.
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_format == "json":
        # Прод: одна строка JSON на лог. Удобно для log aggregator'ов
        # (Loki, ELK, Datadog).
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Dev: читаемый вывод с цветами.
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # ProcessorFormatter используется в stdlib handler'е для ВСЕХ логов,
    # включая uvicorn, aiogram, sqlalchemy.
    formatter = structlog.stdlib.ProcessorFormatter(
        # foreign_pre_chain прогоняется ДО рендера для логов от stdlib-логгеров.
        foreign_pre_chain=shared_processors,
        processors=[
            # strip_log_levels — для ProcessorFormatter (не для structlog pipeline).
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Единственный handler для всего приложения — пишем в stdout (для docker logs).
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    # Очищаем существующие handlers, чтобы не дублировать вывод
    # (uvicorn, например, ставит свой handler при старте).
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Уменьшаем шум от сторонних библиотек по умолчанию.
    # Пользователь может переопределить через LOG_LEVEL.
    for noisy in ("aiogram.event", "aiogram.dispatcher"):
        logging.getLogger(noisy).setLevel(max(level, logging.INFO))

    # structlog pipeline для собственных логгеров (если кто-то использует
    # structlog.get_logger() вместо logging.getLogger()).
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            *shared_processors,
            # wrap_for_formatter конвертирует event_dict в LogRecord,
            # который потом рендерится через ProcessorFormatter (тот же handler).
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Convenience wrapper для получения structlog-логгера.

    Используйте, если хотите structlog-native API (kwargs-style):
        from core.logging import get_logger
        logger = get_logger(__name__)
        logger.info("payment_succeeded", tg_id=123, amount=5000)

    Для обратной совместимости можно продолжать использовать:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("payment_succeeded tg_id=%s amount=%s", 123, 5000)

    Оба варианта проходят через один handler и попадают в один формат.
    """
    return structlog.get_logger(name)
