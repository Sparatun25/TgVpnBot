"""Точка запуска FastAPI приложения."""

import asyncio
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    generate_latest,
    multiprocess,
)
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.base import BaseHTTPMiddleware

from api.admin import router as admin_router
from api.admin_ui import router as admin_ui_router
from api.routes import router
from core import metrics  # noqa: F401  # регистрирует все Counter/Histogram в REGISTRY
from core.config import settings
from core.db import async_session_factory
from core.logging import get_logger, setup_logging
from core.middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from database.init_db import init_db
from services.traffic_collector import collect_traffic_stats

# Настройка логирования ДО создания app и импорта роутеров, чтобы все
# последующие логгеры (включая uvicorn, sqlalchemy) шли через structlog pipeline.
setup_logging()

logger = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Добавляет security-заголовки ко всем ответам.

    - Strict-Transport-Security (HSTS): принуждает браузер использовать HTTPS
      в течение max-age. Включаем только при ответе по HTTPS (proxy-headers).
      В проде nginx уже терминирует TLS и прокидывает X-Forwarded-Proto=https;
      клиент видит наш ответ как защищённый и HSTS активируется.
      В локальной разработке (http://localhost) — не активируется.

    - X-Content-Type-Options: запрещает MIME-sniffing.
    - X-Frame-Options: блокирует embedding в iframe (защита от clickjacking).
    - Referrer-Policy: ограничивает Referer только своим origin.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # HSTS включаем только если запрос пришёл по HTTPS (за nginx).
        forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
        is_https = request.url.scheme == "https" or forwarded_proto == "https"
        if is_https:
            # max-age=31536000 = 1 год. Достаточно долго для production.
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle события приложения."""
    logger.info("app_starting", environment=settings.environment)

    # Production safety net: refuse to start without DB_ENCRYPTION_KEY.
    # Если ключ не задан — connection_url (vpn:// с приватными ключами
    # AmneziaWG) хранится plaintext в БД. Утечка БД = утечка ВСЕХ
    # VPN-ключей пользователей. Падаем сразу, до init_db, чтобы оператор
    # получил явную ошибку в логах при деплое.
    if settings.environment == "production" and settings.db_encryption_key is None:
        raise RuntimeError(
            "DB_ENCRYPTION_KEY не задан в production — connection_url "
            "будет храниться plaintext, утечка БД = утечка VPN-ключей. "
            "Сгенерируйте ключ: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())" '
            "и задайте DB_ENCRYPTION_KEY в .env"
        )

    try:
        await init_db()
    except Exception as exc:
        logger.exception("db_init_failed", error=str(exc))

    # Фоновый сборщик трафика WireGuard. Запускается как отдельная asyncio-задача,
    # чтобы не блокировать event loop и не задерживать старт приложения.
    # Если контейнер Amnezia ещё не развёрнут (dev) или фича выключена — пропускаем.
    traffic_task: asyncio.Task | None = None
    if settings.traffic_collector_enabled:
        traffic_task = asyncio.create_task(
            _traffic_collector_loop(),
            name="traffic_collector",
        )
        logger.info(
            "traffic_collector_started",
            interval=settings.traffic_collect_interval_seconds,
        )
    else:
        logger.info("traffic_collector_disabled")

    try:
        yield
    finally:
        # Корректно останавливаем фоновую задачу при shutdown, чтобы не было
        # висящих корутин в логах uvicorn.
        if traffic_task is not None and not traffic_task.done():
            traffic_task.cancel()
            try:
                await traffic_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("traffic_collector_stop_error", error=str(exc))
        logger.info("app_stopping")


async def _traffic_collector_loop() -> None:
    """Бесконечный цикл сбора трафика из Amnezia-контейнера.

    Логика:
    - Ждём interval секунд.
    - Открываем сессию из async_session_factory (вне FastAPI dependency).
    - Вызываем collect_traffic_stats.
    - При любой ошибке внутри одной итерации — логируем, продолжаем.
      Один неудачный запуск не должен убивать весь цикл.
    - Задача завершается через CancelledError при shutdown.
    """
    interval = max(30, settings.traffic_collect_interval_seconds)
    # Небольшая задержка при старте: даём другим компонентам (БД, Docker)
    # полностью подняться, прежде чем первый запрос пойдёт в Amnezia.
    await asyncio.sleep(5)

    while True:
        try:
            async with async_session_factory() as session:
                result = await collect_traffic_stats(session)
                if not result["container_available"]:
                    logger.warning(
                        "traffic_collector_amnezia_unavailable",
                        hint="контейнер AmneziaWG не отвечает на wg show",
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "traffic_collector_iteration_failed",
                error=str(exc),
            )
        await asyncio.sleep(interval)


app = FastAPI(
    title="OnyxVpn API",
    description="API для Telegram Mini App OnyxVpn",
    version="1.0.0",
    lifespan=lifespan,
)

# RequestIdMiddleware первым: чтобы request_id был доступен во ВСЕХ
# последующих middleware и хэндлерах, в т.ч. в CORS preflight (OPTIONS).
app.add_middleware(RequestIdMiddleware)

# CORS для React Mini App и админки.
# Явно перечисляем методы и заголовки вместо "*" — принцип минимальных привилегий.
# Браузер всё равно посылает preflight только на эти методы/заголовки,
# а нам не нужно открывать дверь PUT/DELETE/PATCH, которые мы не используем.
ALLOWED_CORS_METHODS: list[str] = ["GET", "POST", "DELETE", "OPTIONS"]
ALLOWED_CORS_HEADERS: list[str] = [
    "Authorization",     # Bearer-токены для авторизации
    "Content-Type",      # JSON-тело запросов
    "X-Requested-With",  # стандартный preflight-заголовок
    REQUEST_ID_HEADER,   # для клиентской корреляции логов
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://onyxvpnbot.ru",  # Mini App и админка
        "http://localhost:3000",  # для разработки
    ],
    allow_credentials=True,
    allow_methods=ALLOWED_CORS_METHODS,
    allow_headers=ALLOWED_CORS_HEADERS,
)

# Security headers (HSTS, X-Frame-Options и т.д.) — после CORS, чтобы
# они попадали и в preflight-ответы тоже.
app.add_middleware(SecurityHeadersMiddleware)

# Подключаем роутеры
app.include_router(router)
app.include_router(admin_ui_router)
app.include_router(admin_router)

# Prometheus instrumentator: автоматически собирает http_requests_total,
# http_request_duration_seconds, http_requests_in_progress для каждого
# эндпоинта. /health, /ready, /metrics исключены — нечего мониторить.
Instrumentator(
    should_group_status_codes=True,
    excluded_handlers=["/health", "/ready", "/metrics", "/docs", "/redoc", "/openapi.json"],
).instrument(app)


# ─────────────────────────────────────────────────────────
# Health & Metrics endpoints
# ─────────────────────────────────────────────────────────

@app.get("/health", include_in_schema=False)
async def health_check():
    """Liveness probe: процесс жив и отвечает.

    Не проверяет БД — для этого есть /ready. Используется Docker healthcheck
    и Kubernetes livenessProbe.
    """
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
async def readiness_check():
    """Readiness probe: процесс готов принимать трафик.

    Проверяет подключение к БД через SELECT 1. Если БД недоступна — 503,
    и балансировщик (nginx / k8s service) перестаёт слать запросы до
    восстановления. Используется Kubernetes readinessProbe.
    """
    from sqlalchemy import text

    from core.db import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("readiness_check_failed", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "db": "error"},
        )
    return {"status": "ready", "db": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics(request: Request):
    """Prometheus exposition endpoint.

    В multiprocess-режиме (uvicorn --workers 4 + PROMETHEUS_MULTIPROC_DIR):
    собираем метрики со всех worker'ов через MultiProcessCollector.
    Иначе отдаём дефолтный REGISTRY.

    Авторизация:
    - Если PROMETHEUS_METRICS_TOKEN задан — требуем Authorization: Bearer.
      Используем hmac.compare_digest для защиты от timing-атак.
    - Если не задан — endpoint открыт (как раньше). В production ЗАДАВАЙТЕ
      токен И закрывайте на уровне сети (nginx IP-allowlist).
    """
    metrics_token = settings.prometheus_metrics_token
    if metrics_token is not None:
        auth_header = request.headers.get("authorization", "")
        # Ожидаем формат "Bearer <token>". Парсим без regex для скорости.
        if not auth_header.startswith("Bearer "):
            return Response(
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            )
        presented_token = auth_header[len("Bearer "):]
        # hmac.compare_digest — constant-time, не утекает длина токена через тайминг.
        if not hmac.compare_digest(
            presented_token,
            metrics_token.get_secret_value(),
        ):
            return Response(
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            )

    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
    else:
        data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ─────────────────────────────────────────────────────────
# Обработчики ошибок
# ─────────────────────────────────────────────────────────

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Обработка ошибок валидации."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Обработка непредвиденных ошибок.

    request_id автоматически попадает в лог через structlog contextvars
    (был забинжен в RequestIdMiddleware).
    """
    logger.exception("unhandled_exception", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Внутренняя ошибка сервера"},
    )


# ─────────────────────────────────────────────────────────
# Статические страницы документации
# ─────────────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent / "static"

@app.get("/privacy")
async def privacy_page():
    return FileResponse(STATIC_DIR / "privacy.html")

@app.get("/terms")
async def terms_page():
    return FileResponse(STATIC_DIR / "terms.html")

@app.get("/pricing")
async def pricing_page():
    return FileResponse(STATIC_DIR / "pricing.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
