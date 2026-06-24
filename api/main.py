"""Точка запуска FastAPI приложения."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import router
from api.admin_ui import router as admin_ui_router
from core.config import settings

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle события приложения."""
    logger.info("Приложение запускается")
    yield
    logger.info("Приложение останавливается")


app = FastAPI(
    title="OnyxVpn API",
    description="API для Telegram Mini App OnyxVpn",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS для React Mini App
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-mini-app-domain.com",  # TODO: заменить на реальный домен
        "http://localhost:3000",  # для разработки
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(router)
app.include_router(admin_ui_router)


# Обработчики ошибок
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Обработка ошибок валидации."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Обработка непредвиденных ошибок."""
    logger.exception("Непредвиденная ошибка: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Внутренняя ошибка сервера"},
    )


@app.get("/health")
async def health_check():
    """Проверка здоровья API."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
