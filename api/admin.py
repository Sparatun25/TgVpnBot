"""Админ-панель: метрики и управление подписками."""

import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user_tg_id, security
from core.config import settings
from core.db import async_session_factory, get_session
from database.models import (
    AdminSession,
    BroadcastCampaign,
    BroadcastDelivery,
    BroadcastSegment,
    BroadcastStatus,
    DeliveryStatus,
    Payment,
    PaymentStatus,
    PlanType,
    Subscription,
    User,
)
from services.amnezia import create_client_key, revoke_client_key
from services.broadcast import (
    TEMPLATE_VARIABLES,
    cancel_campaign,
    count_all_segments,
    resolve_audience,
    start_campaign_in_background,
)
from services.traffic_collector import get_user_traffic

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
    total_traffic_rx_bytes: int = Field(
        default=0, description="Суммарный входящий трафик всех пользователей, байт"
    )
    total_traffic_tx_bytes: int = Field(
        default=0, description="Суммарный исходящий трафик всех пользователей, байт"
    )
    active_now: int = Field(
        default=0,
        description="Пользователи с handshake в последние 3 минуты (онлайн прямо сейчас)",
    )
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
    # Трафик через WireGuard-туннель (из User.total_bytes_*). Обновляется
    # фоновым сборщиком каждые N секунд (см. api/main.py lifespan).
    total_bytes_received: int = Field(
        default=0, description="Суммарный скачанный трафик, байт"
    )
    total_bytes_sent: int = Field(
        default=0, description="Суммарный загруженный трафик, байт"
    )
    last_handshake_at: str | None = Field(
        default=None,
        description="UTC ISO timestamp последнего handshake клиента. NULL если ещё не подключался.",
    )
    # Флаги уведомлений о скором окончании триала (из User.notified_*).
    # Admin UI рисует бейджи: «🔔 24ч» если уже отправлено, пусто если нет.
    # Полезно для проверки «кому из истекающих триалов уже ушло уведомление».
    notified_24h: bool = Field(
        default=False,
        description="Отправлено ли уведомление «24ч до окончания»",
    )
    notified_1h: bool = Field(
        default=False,
        description="Отправлено ли уведомление «1ч до окончания»",
    )


class UserTrafficResponse(BaseModel):
    """Детальный трафик пользователя для UI админки."""

    tg_id: int
    username: str | None = None
    total_bytes_received: int
    total_bytes_sent: int
    last_handshake_at: str | None = None
    last_activity_at: str | None = None
    subscription_active: bool
    subscription_expires_at: str | None = None
    subscription_plan_type: str | None = None


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
# Схемы для рассылок (broadcasts)
# ─────────────────────────────────────────────────────────

class BroadcastCreateRequest(BaseModel):
    """Создание новой кампании рассылки.

    На этом этапе создаётся DRAFT-кампания: админ видит размер аудитории
    в preview, может отредактировать текст, и только потом нажимает «Запустить».
    """

    title: str = Field(
        min_length=1, max_length=100,
        description="Внутреннее имя кампании (видно только админу)",
    )
    message_text: str = Field(
        min_length=1, max_length=4096,
        description="HTML-текст сообщения. Поддерживает переменные: "
                    "{first_name}, {username}, {balance}, {days_left}, {plan_type}",
    )
    target_segment: BroadcastSegment = Field(
        description="Сегмент получателей: trial, paid, expired, etc.",
    )


class BroadcastCampaignOut(BaseModel):
    """Кампания в списке/детальном просмотре."""

    id: int
    title: str
    message_text: str
    target_segment: str
    status: str
    created_by_tg_id: int
    total_recipients: int
    sent_count: int
    failed_count: int
    blocked_count: int
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None

    @classmethod
    def from_model(cls, c: BroadcastCampaign) -> "BroadcastCampaignOut":
        return cls(
            id=c.id,
            title=c.title,
            message_text=c.message_text,
            target_segment=c.target_segment.value,
            status=c.status.value,
            created_by_tg_id=c.created_by_tg_id,
            total_recipients=c.total_recipients,
            sent_count=c.sent_count,
            failed_count=c.failed_count,
            blocked_count=c.blocked_count,
            created_at=c.created_at.isoformat(),
            started_at=c.started_at.isoformat() if c.started_at else None,
            finished_at=c.finished_at.isoformat() if c.finished_at else None,
        )


class BroadcastListResponse(BaseModel):
    """Список кампаний с пагинацией."""

    items: list[BroadcastCampaignOut]
    total: int
    page: int
    per_page: int


class BroadcastDeliveryOut(BaseModel):
    """Один получатель в детальном просмотре кампании."""

    id: int
    user_tg_id: int
    username: str | None = None
    status: str
    error_message: str | None = None
    created_at: str
    sent_at: str | None = None


class BroadcastDeliveryListResponse(BaseModel):
    """Список получателей кампании с пагинацией."""

    items: list[BroadcastDeliveryOut]
    total: int
    page: int
    per_page: int
    by_status: dict[str, int] = Field(
        description="Подсчёт по статусам: pending/sent/failed/blocked",
    )


class BroadcastSegmentStatsResponse(BaseModel):
    """Количество юзеров в каждом сегменте (для UI preview)."""

    segments: dict[str, int]
    template_variables: dict[str, str] = Field(
        description="Доступные переменные для шаблона сообщения",
    )


class BroadcastActionResponse(BaseModel):
    """Ответ на start/cancel/delete."""

    id: int
    status: str
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

    # Суммарный трафик всех пользователей через WireGuard. Один запрос с SUM по всем
    # юзерам — дешевле, чем джойнить с активными подписками (трафик хранится на User,
    # а не на Subscription).
    total_traffic_q = select(
        func.coalesce(func.sum(User.total_bytes_received), 0).label("rx"),
        func.coalesce(func.sum(User.total_bytes_sent), 0).label("tx"),
    )
    traffic_row = (await session.execute(total_traffic_q)).one()
    total_traffic_rx_bytes = int(traffic_row.rx or 0)
    total_traffic_tx_bytes = int(traffic_row.tx or 0)

    # "Онлайн прямо сейчас" — пользователи с handshake в последние 3 минуты.
    # WireGuard persistent keepalive у нас 25 сек, так что 3 минуты — щедрый порог:
    # даже если соединение чуть подвисло, пользователь всё ещё считается активным.
    three_min_ago = now - timedelta(minutes=3)
    active_now_q = select(func.count(User.id)).where(
        User.last_handshake_at >= three_min_ago,
    )
    active_now = (await session.execute(active_now_q)).scalar_one()

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
        total_traffic_rx_bytes=total_traffic_rx_bytes,
        total_traffic_tx_bytes=total_traffic_tx_bytes,
        active_now=active_now,
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
            total_bytes_received=sub.user.total_bytes_received or 0,
            total_bytes_sent=sub.user.total_bytes_sent or 0,
            last_handshake_at=(
                sub.user.last_handshake_at.isoformat()
                if sub.user.last_handshake_at
                else None
            ),
            notified_24h=sub.user.notified_24h,
            notified_1h=sub.user.notified_1h,
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
        # Возможный orphan: ключ может ещё быть в Amnezia (scheduler выставил
        # is_active=False ДО revoke — см. services/amnezia.py:check_expired_subscriptions).
        # Не отказываем — даём админу шанс дочистить ключ в Amnezia.
        logger.warning(
            "Админ tg_id=%s повторно вызывает revoke для неактивной подписки id=%s "
            "(uuid=%s) — возможна чистка orphan",
            admin_tg_id, sub.id, sub.uuid[:16] + "...",
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


@router.get("/users/{tg_id}/traffic", response_model=UserTrafficResponse)
async def get_user_traffic_endpoint(
    tg_id: int,
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserTrafficResponse:
    """Детальная информация о трафике конкретного пользователя.

    Возвращает суммарный RX/TX через WireGuard-туннель, время последнего
    handshake (если есть), и связанную подписку. Используется в UI админки
    для детального просмотра карточки пользователя.
    """
    traffic = await get_user_traffic(session, tg_id)
    if traffic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    return UserTrafficResponse(**traffic)


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


# ─────────────────────────────────────────────────────────
# Рассылки (broadcasts)
# ─────────────────────────────────────────────────────────

@router.post("/broadcasts", response_model=BroadcastCampaignOut, status_code=status.HTTP_201_CREATED)
async def create_broadcast(
    body: BroadcastCreateRequest,
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BroadcastCampaignOut:
    """
    Создать новую кампанию рассылки в статусе DRAFT.

    На этом этапе:
    - Резолвится аудитория по сегменту (resolve_audience)
    - Создаётся BroadcastCampaign (status=draft)
    - Создаются BroadcastDelivery строки для каждого получателя (status=pending)

    Кампания остаётся в DRAFT до явного вызова /start. Админ может проверить
    размер аудитории и текст, удалить и создать заново, прежде чем запускать.
    """
    # Резолвим аудиторию — нужно знать размер ДО создания, чтобы вернуть
    # total_recipients сразу. Если сегмент пустой — отказываем, чтобы не
    # плодить пустые кампании.
    audience = await resolve_audience(session, body.target_segment)
    if not audience:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Сегмент '{body.target_segment.value}' не содержит ни одного пользователя",
        )

    # Создаём кампанию
    campaign = BroadcastCampaign(
        title=body.title,
        message_text=body.message_text,
        target_segment=body.target_segment,
        status=BroadcastStatus.DRAFT,
        created_by_tg_id=admin_tg_id,
        total_recipients=len(audience),
    )
    session.add(campaign)
    await session.flush()  # получаем campaign.id

    # Создаём BroadcastDelivery для каждого получателя.
    # bulk_insert_mappings быстрее, чем insert() в цикле, потому что
    # генерирует один INSERT с множеством VALUES-строк вместо N запросов.
    await session.execute(
        BroadcastDelivery.__table__.insert(),
        [
            {
                "campaign_id": campaign.id,
                "user_id": u["user_id"],
                "user_tg_id": u["tg_id"],
                "status": DeliveryStatus.PENDING.value,
            }
            for u in audience
        ],
    )
    await session.commit()
    await session.refresh(campaign)

    logger.info(
        "broadcast_created id=%s segment=%s recipients=%s admin=%s",
        campaign.id, campaign.target_segment, len(audience), admin_tg_id,
    )

    return BroadcastCampaignOut.from_model(campaign)


@router.get("/broadcasts", response_model=BroadcastListResponse)
async def list_broadcasts(
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(ge=1, default=1),
    per_page: int = Query(ge=1, le=100, default=20),
    status_filter: str | None = Query(None, alias="status"),
) -> BroadcastListResponse:
    """Список всех кампаний рассылок с пагинацией и фильтром по статусу."""
    base_query = select(BroadcastCampaign).order_by(BroadcastCampaign.created_at.desc())
    count_query = select(func.count(BroadcastCampaign.id))

    if status_filter:
        try:
            status_enum = BroadcastStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Неизвестный статус: {status_filter}",
            )
        base_query = base_query.where(BroadcastCampaign.status == status_enum)
        count_query = count_query.where(BroadcastCampaign.status == status_enum)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * per_page
    items_q = base_query.offset(offset).limit(per_page)
    items = (await session.execute(items_q)).scalars().all()

    return BroadcastListResponse(
        items=[BroadcastCampaignOut.from_model(c) for c in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/broadcasts/segments/stats", response_model=BroadcastSegmentStatsResponse)
async def get_broadcast_segment_stats(
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BroadcastSegmentStatsResponse:
    """Количество юзеров в каждом сегменте + список переменных шаблона.

    Используется в UI на странице создания рассылки: показывает «Trial: 412»,
    «Paid: 89» и т.п. для быстрого выбора аудитории.
    """
    segments = await count_all_segments(session)
    return BroadcastSegmentStatsResponse(
        segments=segments,
        template_variables=TEMPLATE_VARIABLES,
    )


@router.get("/broadcasts/{campaign_id}", response_model=BroadcastCampaignOut)
async def get_broadcast(
    campaign_id: int,
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BroadcastCampaignOut:
    """Детальная информация о кампании (без списка получателей)."""
    campaign = (
        await session.execute(
            select(BroadcastCampaign).where(BroadcastCampaign.id == campaign_id)
        )
    ).scalar_one_or_none()

    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кампания не найдена",
        )

    return BroadcastCampaignOut.from_model(campaign)


@router.get("/broadcasts/{campaign_id}/deliveries", response_model=BroadcastDeliveryListResponse)
async def get_broadcast_deliveries(
    campaign_id: int,
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(ge=1, default=1),
    per_page: int = Query(ge=1, le=200, default=50),
    status_filter: str | None = Query(None, alias="status"),
) -> BroadcastDeliveryListResponse:
    """Список получателей кампании с фильтром по статусу доставки.

    Используется в UI для просмотра «кому уже отправлено», «кто заблокировал бота»
    и т.п. Соединяемся с User, чтобы достать username для UI без N+1.
    """
    # Проверяем существование кампании
    campaign = (
        await session.execute(
            select(BroadcastCampaign.id).where(BroadcastCampaign.id == campaign_id)
        )
    ).scalar_one_or_none()
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кампания не найдена",
        )

    base_query = (
        select(BroadcastDelivery)
        .join(User, User.id == BroadcastDelivery.user_id, isouter=True)
        .where(BroadcastDelivery.campaign_id == campaign_id)
    )
    count_query = select(func.count(BroadcastDelivery.id)).where(
        BroadcastDelivery.campaign_id == campaign_id,
    )

    if status_filter:
        try:
            status_enum = DeliveryStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Неизвестный статус: {status_filter}",
            )
        base_query = base_query.where(BroadcastDelivery.status == status_enum)
        count_query = count_query.where(BroadcastDelivery.status == status_enum)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * per_page
    items_q = (
        base_query
        .order_by(BroadcastDelivery.id)
        .offset(offset)
        .limit(per_page)
    )
    rows = (await session.execute(items_q)).all()

    # Подсчёт по статусам — отдельный запрос с группировкой. Делается одним
    # вызовом вместо четырёх COUNT-ов.
    by_status_q = (
        select(BroadcastDelivery.status, func.count(BroadcastDelivery.id))
        .where(BroadcastDelivery.campaign_id == campaign_id)
        .group_by(BroadcastDelivery.status)
    )
    by_status_rows = (await session.execute(by_status_q)).all()
    by_status = {s.value: cnt for s, cnt in by_status_rows}

    items = [
        BroadcastDeliveryOut(
            id=row[0].id,
            user_tg_id=row[0].user_tg_id,
            username=row[1].username if row[1] else None,
            status=row[0].status.value,
            error_message=row[0].error_message,
            created_at=row[0].created_at.isoformat(),
            sent_at=row[0].sent_at.isoformat() if row[0].sent_at else None,
        )
        for row in rows
    ]

    return BroadcastDeliveryListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        by_status=by_status,
    )


@router.post("/broadcasts/{campaign_id}/start", response_model=BroadcastActionResponse)
async def start_broadcast(
    campaign_id: int,
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BroadcastActionResponse:
    """
    Запустить рассылку.

    Запускает фоновую asyncio-задачу (services/broadcast.start_campaign).
    Возвращает 202 Accepted сразу, не дожидаясь окончания отправки.
    UI опрашивает /broadcasts/{id} для обновления статуса и счётчиков.

    Повторный вызов на SENDING/COMPLETED/CANCELED → 409 Conflict.
    """
    campaign = (
        await session.execute(
            select(BroadcastCampaign).where(BroadcastCampaign.id == campaign_id)
        )
    ).scalar_one_or_none()

    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кампания не найдена",
        )

    if campaign.status != BroadcastStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Кампания в статусе '{campaign.status.value}', нельзя запустить",
        )

    # Запускаем в фоне. start_campaign сам переведёт кампанию в SENDING
    # (если что-то не так — статус не изменится, останется DRAFT, и админ
    # увидит это при следующем опросе).
    start_campaign_in_background(campaign_id)

    logger.info(
        "broadcast_start_requested campaign_id=%s admin=%s recipients=%s",
        campaign_id, admin_tg_id, campaign.total_recipients,
    )

    return BroadcastActionResponse(
        id=campaign_id,
        status=BroadcastStatus.SENDING.value,
        message=f"Рассылка запущена ({campaign.total_recipients} получателей)",
    )


@router.post("/broadcasts/{campaign_id}/cancel", response_model=BroadcastActionResponse)
async def cancel_broadcast(
    campaign_id: int,
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BroadcastActionResponse:
    """Отменить активную рассылку.

    Ставит Event в services/broadcast._cancel_events — фоновая задача
    завершит текущий батч и выйдет. Если кампания уже завершена —
    возвращает 409 Conflict.
    """
    # Проверяем существование
    exists = (
        await session.execute(
            select(BroadcastCampaign.id).where(BroadcastCampaign.id == campaign_id)
        )
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кампания не найдена",
        )

    ok = await cancel_campaign(campaign_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Кампания уже завершена и не может быть отменена",
        )

    logger.info(
        "broadcast_cancel_requested campaign_id=%s admin=%s",
        campaign_id, admin_tg_id,
    )

    return BroadcastActionResponse(
        id=campaign_id,
        status=BroadcastStatus.CANCELED.value,
        message="Рассылка отменена",
    )


@router.delete("/broadcasts/{campaign_id}", response_model=BroadcastActionResponse)
async def delete_broadcast(
    campaign_id: int,
    admin_tg_id: Annotated[int, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BroadcastActionResponse:
    """Удалить кампанию из истории.

    Нельзя удалить кампанию в SENDING — сначала отмените. Каскадно удаляются
    все BroadcastDelivery (cascade="all, delete-orphan" в модели).
    """
    campaign = (
        await session.execute(
            select(BroadcastCampaign).where(BroadcastCampaign.id == campaign_id)
        )
    ).scalar_one_or_none()

    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кампания не найдена",
        )

    if campaign.status == BroadcastStatus.SENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя удалить рассылку в процессе отправки — сначала отмените",
        )

    title = campaign.title
    await session.delete(campaign)
    await session.commit()

    logger.info(
        "broadcast_deleted campaign_id=%s admin=%s title=%s",
        campaign_id, admin_tg_id, title,
    )

    return BroadcastActionResponse(
        id=campaign_id,
        status="deleted",
        message=f"Кампания «{title}» удалена",
    )
