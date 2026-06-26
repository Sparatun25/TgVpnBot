"""Админ-панель: веб-интерфейс."""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import security, validate_login_widget
from core.config import settings
from core.db import get_session
from database.models import AdminSession

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-ui"])

ADMIN_STATIC_DIR = Path(__file__).parent / "static"


class TelegramLoginData(BaseModel):
    """Данные от Telegram Login Widget."""
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


@router.post("/api/admin/login")
async def admin_login(
    data: TelegramLoginData,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Валидация Telegram Login Widget для админки.

    Создаёт новую AdminSession с TTL (по умолчанию 24 часа) и возвращает
    секретный токен. Клиент хранит токен в sessionStorage и передаёт его
    в Authorization: Bearer <token> при последующих запросах.

    Прежняя схема с передачей tg_id в X-Admin-Tg-Id считалась небезопасной
    (подделка заголовка = полный доступ к админке без аутентификации) и
    удалена из require_admin.
    """
    data_dict = data.model_dump()

    bot_token = settings.bot_token
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BOT_TOKEN не настроен",
        )

    try:
        tg_id = validate_login_widget(data_dict, bot_token.get_secret_value())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Ошибка валидации: {str(e)}",
        )

    if tg_id not in settings.bot_admin_ids:
        logger.warning("Попытка входа в админку: tg_id=%s (не админ)", tg_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён: вы не администратор",
        )

    # Чистим протухшие сессии этого админа, чтобы таблица не пухла.
    await session.execute(
        delete(AdminSession).where(
            AdminSession.tg_id == tg_id,
            AdminSession.expires_at < datetime.now(timezone.utc),
        )
    )

    # Создаём новую сессию.
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    admin_session = AdminSession(
        tg_id=tg_id,
        token=token,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.admin_session_ttl_seconds),
        last_used_at=now,
    )
    session.add(admin_session)
    await session.commit()

    logger.info(
        "Создана admin-сессия для tg_id=%s, истекает %s",
        tg_id,
        admin_session.expires_at.isoformat(),
    )

    return {
        "token": token,
        "expires_at": admin_session.expires_at.isoformat(),
        "tg_id": tg_id,
        "message": "Авторизация успешна",
    }


@router.post("/api/admin/logout")
async def admin_logout(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Завершить текущую admin-сессию (отозвать токен).

    Идемпотентно: если токена нет в БД — возвращает 200 всё равно,
    чтобы клиент мог безопасно вызвать logout при истёкшей сессии.
    """
    if credentials and credentials.credentials:
        token = credentials.credentials
        result = await session.execute(
            delete(AdminSession).where(AdminSession.token == token)
        )
        await session.commit()
        if result.rowcount:
            logger.info("Admin-сессия отозвана (logout)")

    return {"message": "Logged out"}


@router.get("/api/admin/config")
async def admin_config():
    """
    Конфиг для Telegram Login Widget.

    Возвращает bot_username для виджета.
    """
    bot_token = settings.bot_token
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BOT_TOKEN не настроен",
        )

    # Для виджета нужен username бота
    # Временное решение: возвращаем заглушку, нужно будет настроить
    return {
        "bot_username": "Onyx_vpn24_bot",
    }


# ─── Статика админ-панели ────────────────────────────────────────────────


def _admin_static(
    file_path: Path,
    media_type: str | None = None,
    *,
    html: bool = False,
) -> FileResponse:
    """Отдать статический файл админки с правильными Cache-Control.

    HTML (admin.html): no-cache + no-store + must-revalidate.
    Без этого после деплоя браузер может показать старую разметку
    с устаревшими путями к JS — кликнет, получит 404.

    CSS/JS: public, max-age=3600.
    FileResponse автоматически проставляет Last-Modified по mtime файла,
    браузер сделает условный GET и получит 304, если файл не менялся.
    """
    headers = {
        "Cache-Control": (
            "no-cache, no-store, must-revalidate"
            if html
            else "public, max-age=3600"
        ),
        "Pragma": "no-cache" if html else None,
        "Expires": "0" if html else None,
    }
    headers = {k: v for k, v in headers.items() if v is not None}
    return FileResponse(file_path, media_type=media_type, headers=headers)


@router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """Главная страница админ-панели."""
    return _admin_static(ADMIN_STATIC_DIR / "admin.html", html=True)


@router.get("/admin/base.css")
async def admin_base_css():
    return _admin_static(
        ADMIN_STATIC_DIR / "admin-base.css", media_type="text/css"
    )


@router.get("/admin/sidebar.css")
async def admin_sidebar_css():
    return _admin_static(
        ADMIN_STATIC_DIR / "admin-sidebar.css", media_type="text/css"
    )


@router.get("/admin/metrics.css")
async def admin_metrics_css():
    return _admin_static(
        ADMIN_STATIC_DIR / "admin-metrics.css", media_type="text/css"
    )


@router.get("/admin/components.css")
async def admin_components_css():
    return _admin_static(
        ADMIN_STATIC_DIR / "admin-components.css", media_type="text/css"
    )


@router.get("/admin/overlays.css")
async def admin_overlays_css():
    return _admin_static(
        ADMIN_STATIC_DIR / "admin-overlays.css", media_type="text/css"
    )


@router.get("/admin/app.js")
async def admin_app_js():
    return _admin_static(
        ADMIN_STATIC_DIR / "admin-app.js", media_type="application/javascript"
    )


@router.get("/admin/core.js")
async def admin_core_js():
    return _admin_static(
        ADMIN_STATIC_DIR / "admin-core.js", media_type="application/javascript"
    )


@router.get("/admin/views.js")
async def admin_views_js():
    return _admin_static(
        ADMIN_STATIC_DIR / "admin-views.js", media_type="application/javascript"
    )
