"""Админ-панель: метрики и управление подписками."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user_tg_id, security
from core.config import settings
from core.db import get_session
from database.models import Payment, Subscription, User
from services.amnezia import revoke_client_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ─────────────────────────────────────────────────────────
# Auth: проверка, что пользователь — админ
# ─────────────────────────────────────────────────────────

async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> int:
    """
    Зависимость: пропускает только администраторов из bot_admin_ids.

    Поддерживает два способа авторизации:
    1. Telegram Mini App: Authorization: Bearer <initData> — валидация подписи
    2. Браузер (Login Widget): X-Admin-Tg-Id: <tg_id> — проверка по списку админов
    """
    tg_id = None

    # Способ 1: initData от Mini App
    if credentials and credentials.credentials:
        token = credentials.credentials
        # Если токен — число, это tg_id от Login Widget
        if token.isdigit():
            tg_id = int(token)
        else:
            # Иначе это initData — валидируем
            try:
                tg_id = await get_current_user_tg_id(request, credentials)
            except HTTPException:
                pass

    # Способ 2: header X-Admin-Tg-Id от Login Widget
    if tg_id is None:
        admin_tg_id_header = request.headers.get("X-Admin-Tg-Id")
        if admin_tg_id_header and admin_tg_id_header.isdigit():
            tg_id = int(admin_tg_id_header)

    if tg_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необходима авторизация",
        )

    if tg_id not in settings.bot_admin_ids:
        logger.warning("Попытка доступа к админке: tg_id=%s", tg_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён",
        )
    return tg_id


# ─────────────────────────────────────────────────────────
# Pydantic-схемы
# ─────────────────────────────────────────────────────────

class MetricsResponse(BaseModel):
    """Ответ с метриками."""

    total_users: int = Field(description="Всего пользователей")
    active_subscriptions: int = Field(description="Активных подписок (все типы)")
    active_trials: int = Field(description="Активных триалов")
    total_deposits_kopecks: int = Field(description="Сумма успешных пополнений, коп.")
    top_referrers: list[dict] = Field(description="Топ рефералов")


class SubscriptionOut(BaseModel):
    """Подписка в списке."""

    id: int
    user_tg_id: int
    username: str | None = None
    uuid: str
    plan_type: str
    expires_at: str
    is_active: bool
    created_at: str


class SubscriptionsListResponse(BaseModel):
    """Список подписок с пагинацией."""

    items: list[SubscriptionOut]
    total: int
    page: int
    per_page: int


class ExtendRequest(BaseModel):
    """Запрос на продление подписки."""

    days: int = Field(ge=1, le=365, description="На сколько дней продлить")


class ExtendResponse(BaseModel):
    """Результат продления."""

    id: int
    new_expires_at: str
    message: str


class RevokeResponse(BaseModel):
    """Результат отзыва ключа."""

    id: int
    message: str


# ─────────────────────────────────────────────────────────
# Эндпоинты
# ─────────────────────────────────────────────────────────

@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MetricsResponse:
    """
    Общая статистика OnyxVpn.

    Возвращает:
    - total_users: количество зарегистрированных пользователей
    - active_subscriptions: все активные подписки (trial + paid)
    - active_trials: только триалы
    - total_deposits_kopecks: сумма успешных платежей через СБП
    - top_referrers: топ-5 пригласивших по количеству рефералов
    """
    now = datetime.now(timezone.utc)

    # Всего пользователей
    total_users_q = select(func.count(User.id))
    total_users = (await session.execute(total_users_q)).scalar_one()

    # Активные подписки
    active_subs_q = select(func.count(Subscription.id)).where(
        Subscription.is_active == True,
        Subscription.expires_at > now,
    )
    active_subscriptions = (await session.execute(active_subs_q)).scalar_one()

    # Активные триалы
    active_trials_q = select(func.count(Subscription.id)).where(
        Subscription.is_active == True,
        Subscription.plan_type == "trial",
        Subscription.expires_at > now,
    )
    active_trials = (await session.execute(active_trials_q)).scalar_one()

    # Сумма успешных пополнений
    total_deposits_q = select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.status == "success",
    )
    total_deposits_kopecks = (await session.execute(total_deposits_q)).scalar_one()

    # Топ-5 рефералов (по количеству приглашённых)
    top_referrers_q = (
        select(
            User.referred_by_id,
            func.count(User.id).label("ref_count"),
        )
        .where(User.referred_by_id.isnot(None))
        .group_by(User.referred_by_id)
        .order_by(func.count(User.id).desc())
        .limit(5)
    )
    top_result = await session.execute(top_referrers_q)
    top_rows = top_result.all()

    # Обогащаем данными о пригласивших
    top_referrers = []
    for referred_by_id, ref_count in top_rows:
        referrer_q = select(User).where(User.tg_id == referred_by_id)
        referrer = (await session.execute(referrer_q)).scalar_one_or_none()
        top_referrers.append({
            "tg_id": referred_by_id,
            "username": referrer.username if referrer else None,
            "ref_count": ref_count,
        })

    return MetricsResponse(
        total_users=total_users,
        active_subscriptions=active_subscriptions,
        active_trials=active_trials,
        total_deposits_kopecks=total_deposits_kopecks,
        top_referrers=top_referrers,
    )


@router.get("/subscriptions", response_model=SubscriptionsListResponse)
async def list_subscriptions(
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(ge=1, default=1, description="Страница"),
    per_page: int = Query(ge=1, le=100, default=20, description="На странице"),
    search_tg_id: int | None = Query(None, description="Поиск по tg_id"),
    status_filter: str | None = Query(None, description="Фильтр: active / expired / trial"),
) -> SubscriptionsListResponse:
    """
    Список всех подписок с пагинацией и фильтрами.

    Фильтры:
    - search_tg_id: поиск по Telegram ID пользователя
    - status_filter:
      - "active" — только активные (is_active=True, expires_at > now)
      - "expired" — только истёкшие (expires_at <= now)
      - "trial" — только триалы (plan_type="trial")
    """
    now = datetime.now(timezone.utc)

    # Базовый запрос
    base_query = select(Subscription).join(User)
    count_query = select(func.count(Subscription.id)).join(User)

    # Фильтр по tg_id
    if search_tg_id is not None:
        base_query = base_query.where(User.tg_id == search_tg_id)
        count_query = count_query.where(User.tg_id == search_tg_id)

    # Фильтр по статусу
    if status_filter == "active":
        base_query = base_query.where(
            Subscription.is_active == True,
            Subscription.expires_at > now,
        )
        count_query = count_query.where(
            Subscription.is_active == True,
            Subscription.expires_at > now,
        )
    elif status_filter == "expired":
        base_query = base_query.where(Subscription.expires_at <= now)
        count_query = count_query.where(Subscription.expires_at <= now)
    elif status_filter == "trial":
        base_query = base_query.where(Subscription.plan_type == "trial")
        count_query = count_query.where(Subscription.plan_type == "trial")

    # Общее количество (до пагинации)
    total = (await session.execute(count_query)).scalar_one()

    # Пагинация
    offset = (page - 1) * per_page
    items_query = (
        base_query
        .options(selectinload(Subscription.user))
        .order_by(Subscription.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )

    result = await session.execute(items_query)
    subs = result.scalars().all()

    items = [
        SubscriptionOut(
            id=sub.id,
            user_tg_id=sub.user.tg_id,
            username=sub.user.username,
            uuid=sub.uuid,
            plan_type=sub.plan_type,
            expires_at=sub.expires_at.isoformat(),
            is_active=sub.is_active,
            created_at=sub.created_at.isoformat(),
        )
        for sub in subs
    ]

    return SubscriptionsListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/subscriptions/{subscription_id}/extend", response_model=ExtendResponse)
async def extend_subscription(
    subscription_id: int,
    body: ExtendRequest,
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ExtendResponse:
    """
    Продлить подписку вручную.

    Сдвигает expires_at на указанное количество дней вперёд.
    Если подписка уже истекла — считает от текущего момента.
    """
    # Ищем подписку
    query = select(Subscription).where(Subscription.id == subscription_id)
    result = await session.execute(query)
    sub = result.scalar_one_or_none()

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Подписка не найдена",
        )

    # Сдвигаем expires_at: от now если уже истекла, иначе от текущего expires_at
    now = datetime.now(timezone.utc)
    base = max(sub.expires_at, now)
    new_expires = base + timedelta(days=body.days)

    sub.expires_at = new_expires

    # Если подписка была неактивна (истекла) — реактивируем
    if not sub.is_active:
        sub.is_active = True
        logger.info(
            "Подписка %s реактивирована админом tg_id=%s (+%d дней)",
            subscription_id,
            admin_tg_id,
            body.days,
        )
    else:
        logger.info(
            "Подписка %s продлена админом tg_id=%s (+%d дней)",
            subscription_id,
            admin_tg_id,
            body.days,
        )

    await session.commit()

    return ExtendResponse(
        id=sub.id,
        new_expires_at=new_expires.isoformat(),
        message=f"Подписка продлена на {body.days} дн.",
    )


@router.delete("/subscriptions/{subscription_id}/revoke", response_model=RevokeResponse)
async def revoke_subscription(
    subscription_id: int,
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RevokeResponse:
    """
    Принудительно отозвать ключ Amnezia и деактивировать подписку.

    Вызывает revoke_client_key из сервиса Amnezia (Docker).
    """
    # Ищем подписку
    query = select(Subscription).where(Subscription.id == subscription_id)
    result = await session.execute(query)
    sub = result.scalar_one_or_none()

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Подписка не найдена",
        )

    if not sub.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Подписка уже неактивна",
        )

    # Отзываем ключ через Amnezia
    success = await revoke_client_key(sub.uuid)

    if not success:
        logger.error(
            "Не удалось отозвать ключ %s через Amnezia (админ tg_id=%s)",
            sub.uuid,
            admin_tg_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось отозвать ключ из Amnezia",
        )

    # Деактивируем в БД
    sub.is_active = False
    await session.commit()

    logger.info(
        "Ключ %s отозван админом tg_id=%s (subscription_id=%s)",
        sub.uuid,
        admin_tg_id,
        subscription_id,
    )

    return RevokeResponse(
        id=subscription_id,
        message="Ключ отозван",
    )
