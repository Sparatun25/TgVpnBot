"""Админ-панель: метрики и управление подписками."""

import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user_tg_id, security
from core.config import settings
from core.db import get_session
from database.models import AdminSession, Payment, PaymentStatus, PlanType, Subscription, User
from services.amnezia import create_client_key, revoke_client_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ─────────────────────────────────────────────────────────
# Auth: проверка, что пользователь — админ
# ─────────────────────────────────────────────────────────

async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> int:
    """
    Зависимость: пропускает только администраторов из bot_admin_ids.

    Поддерживает два способа авторизации (оба через Authorization: Bearer):

    1. AdminSession-токен (создаётся /api/admin/login после Login Widget).
       Случайный URL-safe токен с TTL. Ищется в таблице admin_sessions.
       При истечении — сессия удаляется (lazy cleanup) и возвращается 401.
       Каждый успешный запрос обновляет last_used_at.

    2. initData от Telegram Mini App (для будущей интеграции админ-интерфейса
       в Mini App). Валидируется по HMAC-SHA256 подписи с auth_date ≤ 5 мин.

    Прежняя схема X-Admin-Tg-Id / числовой Bearer удалена: любой желающий мог
    подставить произвольный tg_id из bot_admin_ids и получить полный доступ
    к админке без аутентификации.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необходима авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    tg_id: int | None = None

    # Способ 1: AdminSession-токен из БД
    session_q = select(AdminSession).where(AdminSession.token == token)
    admin_session = (await session.execute(session_q)).scalar_one_or_none()

    if admin_session is not None:
        now = datetime.now(timezone.utc)
        if admin_session.expires_at < now:
            # Сессия протухла — удаляем лениво при первом запросе после истечения
            await session.delete(admin_session)
            await session.commit()
            logger.info(
                "Admin-сессия для tg_id=%s истекла и удалена",
                admin_session.tg_id,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Сессия истекла, войдите снова через Telegram",
            )
        tg_id = admin_session.tg_id
        # Обновляем last_used_at — диагностика активности админов
        admin_session.last_used_at = now
        await session.commit()
    else:
        # Способ 2: initData от Telegram Mini App
        try:
            tg_id = await get_current_user_tg_id(request, credentials)
        except HTTPException:
            tg_id = None

    if tg_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный или просроченный токен",
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
    balance: int = 0
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


class TopUpRequest(BaseModel):
    """Запрос на начисление баланса."""

    amount_rubles: float = Field(ge=0.01, description="Сумма в рублях")
    comment: str | None = Field(default=None, description="Комментарий")


class TopUpResponse(BaseModel):
    """Результат начисления баланса."""

    user_tg_id: int
    username: str | None
    old_balance: int
    new_balance: int
    amount_rubles: float
    message: str


class ClearAllRequest(BaseModel):
    """Запрос на очистку всех подписок.

    Требует ввод секретной фразы для защиты от случайного клика в UI
    или выполнения деструктивного действия ботом/скриптом.
    """

    confirmation: str = Field(
        description="Секретная фраза-подтверждение, чтобы исключить случайное удаление",
    )


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
        Subscription.plan_type == PlanType.TRIAL,
        Subscription.expires_at > now,
    )
    active_trials = (await session.execute(active_trials_q)).scalar_one()

    # Сумма успешных пополнений.
    # YooKassa в webhook присылает статус "succeeded" (см. api/routes.py webhook handler),
    # поэтому фильтруем по этому значению. "success" использовался в ранней версии и сейчас
    # не пишется в БД.
    total_deposits_q = select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.status == PaymentStatus.SUCCEEDED,
    )
    total_deposits_kopecks = (await session.execute(total_deposits_q)).scalar_one()

    # Топ-5 рефералов (по количеству приглашённых).
    # Один запрос с JOIN вместо N+1: считаем рефералов в подзапросе,
    # затем джойним с User по tg_id, чтобы получить username без N+1.
    ref_count_subq = (
        select(
            User.referred_by_id.label("referred_by_id"),
            func.count(User.id).label("ref_count"),
        )
        .where(User.referred_by_id.isnot(None))
        .group_by(User.referred_by_id)
        .subquery()
    )
    top_referrers_q = (
        select(
            ref_count_subq.c.referred_by_id,
            ref_count_subq.c.ref_count,
            User.username,
        )
        .join(User, User.tg_id == ref_count_subq.c.referred_by_id)
        .order_by(ref_count_subq.c.ref_count.desc())
        .limit(5)
    )
    top_result = await session.execute(top_referrers_q)
    top_rows = top_result.all()

    top_referrers = [
        {
            "tg_id": referred_by_id,
            "username": username,
            "ref_count": ref_count,
        }
        for referred_by_id, ref_count, username in top_rows
    ]

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
        base_query = base_query.where(Subscription.plan_type == PlanType.TRIAL)
        count_query = count_query.where(Subscription.plan_type == PlanType.TRIAL)

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
            balance=sub.user.balance,
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


# Секретная фраза для подтверждения очистки всех подписок.
# Хранится в коде намеренно — это не пароль, а защита от случайного клика.
# Админ видит её в админке UI и должен сознательно ввести.
CLEAR_ALL_CONFIRMATION_PHRASE = "DELETE_ALL_SUBSCRIPTIONS"


@router.delete("/subscriptions/clear-all")
async def clear_all_subscriptions(
    body: ClearAllRequest,
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """
    Очистить все подписки из таблицы.

    Деструктивная операция: требует ввод фразы-подтверждения
    (CLEAR_ALL_CONFIRMATION_PHRASE) в теле запроса.
    """
    if body.confirmation != CLEAR_ALL_CONFIRMATION_PHRASE:
        logger.warning(
            "Попытка clear-all с неверной фразой от админа tg_id=%s",
            admin_tg_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверная фраза-подтверждение",
        )

    # Получаем количество подписок перед удалением
    count_query = select(func.count(Subscription.id))
    count_result = await session.execute(count_query)
    total_count = count_result.scalar_one()

    # Удаляем все подписки
    delete_query = delete(Subscription)
    await session.execute(delete_query)
    await session.commit()

    logger.info(
        "Админ tg_id=%s очистил таблицу подписок (удалено %d записей)",
        admin_tg_id,
        total_count,
    )

    return {
        "success": True,
        "message": f"Удалено {total_count} подписок",
        "deleted_count": total_count,
    }


# ─────────────────────────────────────────────────────────
# Начисление баланса
# ─────────────────────────────────────────────────────────

@router.post("/users/{tg_id}/topup", response_model=TopUpResponse)
async def topup_user_balance(
    tg_id: int,
    body: TopUpRequest,
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TopUpResponse:
    """
    Начислить баланс пользователю вручную.

    Сумма в рублях, в БД хранится в копейках.
    """
    # Ищем пользователя по tg_id
    query = select(User).where(User.tg_id == tg_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    old_balance = user.balance
    amount_kopecks = int(round(body.amount_rubles * 100))
    user.balance += amount_kopecks
    await session.commit()

    logger.info(
        "Админ tg_id=%s начислил %s руб. пользователю tg_id=%s (баланс: %s → %s коп.)",
        admin_tg_id,
        body.amount_rubles,
        tg_id,
        old_balance,
        user.balance,
    )

    return TopUpResponse(
        user_tg_id=user.tg_id,
        username=user.username,
        old_balance=old_balance,
        new_balance=user.balance,
        amount_rubles=body.amount_rubles,
        message=f"Начислено {body.amount_rubles} ₽",
    )


# ─────────────────────────────────────────────────────────
# Debug endpoint для тестирования vpn:// ключей
# ─────────────────────────────────────────────────────────

@router.get("/debug/vpn-key")
async def debug_vpn_key(
    admin_tg_id: Annotated[int, Depends(require_admin)],
) -> dict:
    """
    Генерирует тестовый vpn:// ключ и возвращает его структуру для отладки.

    Показывает:
    - Полный vpn:// URL
    - Декодированный JSON payload
    - Конфигурацию awg
    """
    try:
        # Генерируем тестовый ключ
        vpn_url, client_pub_key = await create_client_key(
            user_id=999999, is_trial=True, plan_type="trial",
        )

        # Декодируем для проверки
        encoded_part = vpn_url.replace("vpn://", "")
        decoded_bytes = base64.b64decode(encoded_part)
        payload = json.loads(decoded_bytes.decode("utf-8"))

        return {
            "success": True,
            "vpn_url": vpn_url,
            "client_pub_key": client_pub_key,
            "decoded_payload": payload,
            "awg_config": payload["containers"][0]["awg"],
            "container_field": payload["containers"][0]["container"],
        }
    except Exception as e:
        logger.exception("Ошибка генерации debug ключа: %s", e)
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }
