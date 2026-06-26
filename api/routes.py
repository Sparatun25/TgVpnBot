"""API роуты для Mini App."""

import hashlib
import hmac
import ipaddress
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user_tg_id
from core.config import settings
from core.crypto import decrypt_connection_url, encrypt_connection_url
from core.db import get_session
from core.metrics import (
    payment_webhook_rejected_total,
    payments_amount_total_kopecks,
    payments_created_total,
    payments_succeeded_total,
    subscription_purchases_total,
    trial_activations_total,
)
from core.rate_limit import trial_limiter
from database.models import Payment, PaymentStatus, PlanType, Subscription, User
from services.amnezia import create_client_key
from services.payment_sbp import YooKassaPaymentError, create_sbp_payment

logger = logging.getLogger(__name__)

# IP-адреса ЮKassa для webhook (официальный список)
YOOKASSA_IP_RANGES = [
    ipaddress.ip_network("185.71.76.0/27"),
    ipaddress.ip_network("185.71.77.0/27"),
    ipaddress.ip_network("77.75.153.0/25"),
    ipaddress.ip_network("77.75.154.128/25"),
    ipaddress.ip_address("77.75.156.11"),
    ipaddress.ip_address("77.75.156.35"),
    ipaddress.ip_address("127.0.0.1"),  # Для локального тестирования
]


# ─────────────────────────────────────────────────────────
# Pydantic-модели запросов (защита от невалидных payload'ов)
# ─────────────────────────────────────────────────────────

# Идентификаторы тарифов — только из белого списка, никаких произвольных строк.
TariffId = Literal["monthly", "quarter", "year"]


class PurchaseRequest(BaseModel):
    """Запрос на покупку/продление подписки за баланс."""

    model_config = ConfigDict(extra="forbid")

    tariff_id: TariffId = Field(description="ID тарифа: monthly, quarter или year")


class CreatePaymentRequest(BaseModel):
    """Запрос на создание платежа через СБП (ЮKassa).

    Границы суммы — 10 ₽ минимум, 100 000 ₽ максимум. Проверка здесь
    дублируется в логике ниже, чтобы вернуть более понятное сообщение
    об ошибке, но главное — отсеять мусор ещё до похода в БД/ЮKassa.
    """

    model_config = ConfigDict(extra="forbid")

    amount_kopecks: int = Field(
        ge=1000,
        le=10_000_000,
        description="Сумма пополнения в копейках (1000 = 10 ₽, 10_000_000 = 100 000 ₽)",
    )


class YooKassaWebhookPayload(BaseModel):
    """Webhook от ЮKassa.

    Поля — подмножество реального payload'а ЮKassa: нас интересуют только
    payment_id и status. amount/user_id берём из БД — payload'у не доверяем.
    """

    model_config = ConfigDict(extra="ignore")

    payment_id: str = Field(min_length=1, description="ID платежа в нашей системе")
    status: str = Field(min_length=1, description="Статус платежа")


async def verify_yookassa_ip(request: Request) -> None:
    """Проверяет, что запрос пришел с IP-адреса ЮKassa."""
    client_ip = request.client.host if request.client else None

    if not client_ip:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Не удалось определить IP-адрес",
        )

    try:
        client_addr = ipaddress.ip_address(client_ip)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Некорректный IP-адрес",
        )

    # Проверяем, находится ли IP в разрешённых диапазонах
    for allowed in YOOKASSA_IP_RANGES:
        if isinstance(allowed, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
            if client_addr in allowed:
                return
        elif client_addr == allowed:
            return

    logger.warning("Попытка доступа к webhook с неразрешённого IP: %s", client_ip)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Доступ запрещён",
    )

router = APIRouter(prefix="/api", tags=["mini-app"])

# Тарифы: id -> {price_kopecks, days, name}
TARIFFS = {
    "monthly": {"price_kopecks": 24900, "days": 30, "name": "Месяц"},
    "quarter": {"price_kopecks": 65000, "days": 90, "name": "3 месяца"},
    "year": {"price_kopecks": 115000, "days": 365, "name": "Год"},
}

# Эмпирический таймаут: время от создания ключа до первого пакета на сервере.
# Используется как эвристика для авто-перехода WaitingScreen → SuccessScreen,
# пока нет настоящего счётчика трафика на AmneziaWG-сервере.
ACTIVATION_GRACE_SECONDS = 120


@router.get("/tariffs")
async def get_tariffs() -> dict:
    """Список доступных тарифов."""
    return {
        "tariffs": [
            {
                "id": tid,
                "name": t["name"],
                "price_kopecks": t["price_kopecks"],
                "price_rubles": t["price_kopecks"] / 100,
                "days": t["days"],
            }
            for tid, t in TARIFFS.items()
        ]
    }


@router.get("/subscription/status")
async def get_subscription_status(
    tg_id: int = Depends(get_current_user_tg_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Статус подписки для WaitingScreen.

    Возвращает:
    - active: есть ли активная (не истёкшая) подписка
    - auto_advance_eligible: истёк ли grace-период после создания ключа.
      Эвристика: заменяет настоящую проверку трафика на AmneziaWG-сервере,
      которой у нас пока нет. Не отражает факт подключения — только время
      с момента выдачи ключа. Использовать только для авто-перехода в onboarding;
      для биллинга/аналитики поле не предназначено.
    - seconds_since_creation: секунд с момента создания последней активной подписки.
    """
    now = datetime.now(timezone.utc)

    query = select(User).where(User.tg_id == tg_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        return {
            "active": False,
            "auto_advance_eligible": False,
            "seconds_since_creation": 0,
        }

    sub_query = (
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.is_active == True,
            Subscription.expires_at > now,
        )
        .order_by(Subscription.created_at.desc())
    )
    sub_result = await session.execute(sub_query)
    active_sub = sub_result.scalar_one_or_none()

    if not active_sub:
        return {
            "active": False,
            "auto_advance_eligible": False,
            "seconds_since_creation": 0,
        }

    seconds_since = (now - active_sub.created_at).total_seconds()
    auto_advance_eligible = seconds_since > ACTIVATION_GRACE_SECONDS

    return {
        "active": True,
        "auto_advance_eligible": auto_advance_eligible,
        "seconds_since_creation": int(seconds_since),
    }


@router.get("/profile")
async def get_profile(
    tg_id: int = Depends(get_current_user_tg_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Получить профиль пользователя.

    Возвращает баланс, статус подписки и ссылку на ключ.
    """
    # Ищем пользователя + батчем подтягиваем все его подписки одним запросом.
    # Раньше делали 3 отдельных SELECT (user, active_sub, trial) + 1 на referral_count.
    # Теперь 2 запроса: User+selectinload(subscriptions), затем count(User).
    now = datetime.now(timezone.utc)

    query = (
        select(User)
        .where(User.tg_id == tg_id)
        .options(selectinload(User.subscriptions))
    )
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    # Активная подписка — самая свежая из тех, что не истекла.
    # Сортируем по created_at desc, берём первую подходящую.
    active_sub = next(
        (
            s for s in sorted(user.subscriptions, key=lambda s: s.created_at, reverse=True)
            if s.is_active and s.expires_at > now
        ),
        None,
    )
    # Триал когда-либо использовался — просто проверяем флаг.
    has_used_trial = any(s.plan_type == PlanType.TRIAL for s in user.subscriptions)

    # Сколько пользователей пришло по реферальному коду текущего юзера.
    # referred_by_id хранит tg_id пригласившего (см. database/models.py).
    referral_count_q = select(func.count(User.id)).where(User.referred_by_id == tg_id)
    referral_count = (await session.execute(referral_count_q)).scalar_one()

    return {
        "balance": user.balance,
        "referral_code": user.referral_code,
        "referral_count": referral_count,
        "subscription": {
            "active": active_sub is not None,
            "plan_type": active_sub.plan_type if active_sub else None,
            "expires_at": active_sub.expires_at.isoformat() if active_sub else None,
            "connection_url": decrypt_connection_url(active_sub.connection_url) if active_sub and active_sub.connection_url else None,
        },
        "has_used_trial": has_used_trial,
    }


@router.post("/subscription/trial")
async def activate_trial(
    tg_id: int = Depends(get_current_user_tg_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Активировать 3-дневный триал.

    Проверяет, что пользователь ещё не использовал триал.
    """
    # Rate-limit: 5 попыток в минуту на tg_id.
    # Trial — операция одноразовая (см. has_used_trial ниже), лимит защищает от:
    # - двойных кликов при флапающем соединении,
    # - брутфорса с целью найти уязвимость,
    # - нагрузки на Amnezia-контейнер (генерация ключа — дорогая операция).
    if not await trial_limiter.allow(tg_id):
        logger.warning("Rate limit на /subscription/trial для tg_id=%s", tg_id)
        trial_activations_total.labels(result="rate_limited").inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток. Подождите минуту.",
        )

    # Ищем пользователя с блокировкой строки (SELECT FOR UPDATE).
    # Это сериализует параллельные запросы триала для одного tg_id:
    # второй запрос будет ждать завершения первого и увидит уже созданный
    # триал на этапе проверки existing_trial ниже — вернёт чистый 409.
    # Защита defense-in-depth: основной барьер — partial unique index
    # uq_subscriptions_one_trial_per_user (D11), он отвергает дубль
    # на уровне БД даже без явной блокировки.
    query = select(User).where(User.tg_id == tg_id).with_for_update()
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        # Нового пользователя нельзя заблокировать (строки ещё нет).
        # В этом случае защита — UNIQUE(tg_id) на users (не даст создать дубль)
        # и D11 на subscriptions. На следующий запрос /trial пользователь уже
        # существует, и FOR UPDATE сработает как обычно.
        user = User(tg_id=tg_id)
        session.add(user)
        await session.flush()

    # Проверяем, есть ли уже триал
    trial_query = select(Subscription).where(
        Subscription.user_id == user.id,
        Subscription.plan_type == PlanType.TRIAL,
    )
    trial_result = await session.execute(trial_query)
    existing_trial = trial_result.scalar_one_or_none()

    if existing_trial:
        trial_activations_total.labels(result="already_used").inc()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Триал уже был активирован",
        )

    # Проверяем, нет ли активной подписки
    now = datetime.now(timezone.utc)
    active_query = select(Subscription).where(
        Subscription.user_id == user.id,
        Subscription.is_active == True,
        Subscription.expires_at > now,
    )
    active_result = await session.execute(active_query)
    active_sub = active_result.scalar_one_or_none()

    if active_sub:
        trial_activations_total.labels(result="already_used").inc()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Уже есть активная подписка",
        )

    # Генерируем ключ Amnezia
    try:
        connection_url, client_pub_key = await create_client_key(
            user.id, is_trial=True, plan_type="trial",
        )
    except RuntimeError as e:
        logger.error("Ошибка создания ключа Amnezia: %s", e)
        trial_activations_total.labels(result="error").inc()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось создать VPN-ключ",
        ) from e

    # Создаём подписку
    expires_at = now + timedelta(days=settings.trial_days)
    subscription = Subscription(
        user_id=user.id,
        uuid=client_pub_key,  # Сохраняем public key для отзыва ключа
        plan_type=PlanType.TRIAL,
        expires_at=expires_at,
        is_active=True,
        connection_url=encrypt_connection_url(connection_url),
    )
    session.add(subscription)

    # Устанавливаем время создания ключа для отслеживания неактивных
    user.key_created_at = now

    await session.commit()

    trial_activations_total.labels(result="success").inc()

    return {
        "message": "Триал активирован",
        "expires_at": expires_at.isoformat(),
        "connection_url": connection_url,
    }


@router.post("/subscription/purchase")
async def purchase_subscription(
    payload: PurchaseRequest,
    tg_id: int = Depends(get_current_user_tg_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Купить подписку за баланс.

    Ожидает:
    - tariff_id: id тарифа (monthly, quarter, year)

    Логика:
    1. Проверяет наличие тарифа
    2. Проверяет баланс пользователя
    3. Если есть активная подписка — продлевает её
    4. Если нет — создаёт новую
    5. Списывает деньги с баланса
    """
    # Pydantic PurchaseRequest уже гарантирует, что tariff_id ∈ {"monthly", "quarter", "year"}.
    tariff_id = payload.tariff_id

    if tariff_id not in TARIFFS:
        # Страховка от рассогласования модели и TARIFFS — на случай если
        # кто-то добавит тариф в модель, но забудет в словарь.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный тариф",
        )

    tariff = TARIFFS[tariff_id]
    price = tariff["price_kopecks"]
    days = tariff["days"]

    # Ищем пользователя с блокировкой строки (SELECT FOR UPDATE).
    # Сериализует параллельные покупки: два одновременных запроса не смогут
    # прочитать один и тот же баланс и списать его дважды.
    # Defense-in-depth: основная защита — CHECK balance >= 0 (D9),
    # он отвергнет второй UPDATE уже на уровне БД.
    query = select(User).where(User.tg_id == tg_id).with_for_update()
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    # Проверяем баланс
    if user.balance < price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недостаточно средств. Нужно {price / 100:.2f} ₽, на балансе {user.balance / 100:.2f} ₽",
        )

    now = datetime.now(timezone.utc)

    # Проверяем активную подписку
    active_query = select(Subscription).where(
        Subscription.user_id == user.id,
        Subscription.is_active == True,
        Subscription.expires_at > now,
    )
    active_result = await session.execute(active_query)
    active_sub = active_result.scalar_one_or_none()

    if active_sub:
        # Продлеваем существующую подписку
        # Если подписка заканчивается в будущем — добавляем дни к текущей дате окончания
        # Если уже закончилась — добавляем дни к сейчас
        base_date = max(active_sub.expires_at, now)
        new_expires = base_date + timedelta(days=days)
        active_sub.expires_at = new_expires
        active_sub.plan_type = PlanType(tariff_id)
        # Ключ НЕ ротируем: пользователь уже подключён, и выдача нового
        # ключа требует повторного импорта в AmneziaVPN — это сломает
        # работающее соединение. Если ключ скомпрометирован, админ может
        # отозвать его через /api/admin/subscriptions/{id}/revoke.

        subscription = active_sub
        action = "продлена"
    else:
        # Создаём новую подписку
        # Генерируем ключ Amnezia
        try:
            connection_url, client_pub_key = await create_client_key(
                user.id, is_trial=False, plan_type=tariff_id,
            )
        except RuntimeError as e:
            logger.error("Ошибка создания ключа Amnezia: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Не удалось создать VPN-ключ",
            ) from e

        expires_at = now + timedelta(days=days)
        subscription = Subscription(
            user_id=user.id,
            uuid=client_pub_key,
            plan_type=PlanType(tariff_id),
            expires_at=expires_at,
            is_active=True,
            connection_url=encrypt_connection_url(connection_url),
        )
        session.add(subscription)
        action = "активирована"

    # Списываем деньги
    user.balance -= price

    await session.commit()

    # Метрика: фиксируем факт покупки. action_label — английский аналог
    # русского "action" для совместимости с Prometheus label naming convention
    # (английские метки проще агрегировать в Grafana).
    action_label = "extended" if action == "продлена" else "new"
    subscription_purchases_total.labels(tariff_id=tariff_id, action=action_label).inc()

    logger.info(
        "Подписка %s для user_tg_id=%s: тариф=%s, цена=%d коп, баланс: %d → %d коп",
        action,
        tg_id,
        tariff_id,
        price,
        user.balance + price,
        user.balance,
    )

    return {
        "message": f"Подписка {action} до {subscription.expires_at.strftime('%d.%m.%Y')}",
        "expires_at": subscription.expires_at.isoformat(),
        "connection_url": decrypt_connection_url(subscription.connection_url) if subscription.connection_url else None,
        "plan_type": subscription.plan_type,
        "balance_remaining": user.balance,
    }


@router.post("/payment/create")
async def create_payment(
    payload: CreatePaymentRequest,
    tg_id: int = Depends(get_current_user_tg_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Создать платеж через СБП (ЮKassa).

    Ожидает:
    - amount_kopecks: сумма пополнения в копейках

    Возвращает:
    - payment_url: ссылка для оплаты
    - qr_code: QR-код для СБП (base64)
    - payment_id: ID платежа
    """
    # Pydantic CreatePaymentRequest уже проверил: тип int, диапазон 1000..10_000_000 копеек,
    # лишних полей нет (extra="forbid"). Дополнительных проверок не требуется.
    amount_kopecks = payload.amount_kopecks

    # Проверяем, что пользователь существует
    query = select(User).where(User.tg_id == tg_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    amount_rubles = amount_kopecks / 100

    # STUB MODE: пока нет реального провайдера — зачисляем сразу.
    if settings.payment_stub_mode:
        payment_id_str = f"stub_{uuid.uuid4().hex[:16]}"
        payment = Payment(
            user_id=user.id,
            amount=amount_kopecks,
            payment_id=payment_id_str,
            status=PaymentStatus.SUCCEEDED,
        )
        # Сразу зачисляем на баланс
        user.balance += amount_kopecks
        session.add(payment)
        await session.commit()

        # Метрики: stub-платежи сразу "succeeded", поэтому ивентим и
        # payments_created_total, и payments_succeeded_total, и revenue.
        payments_created_total.labels(kind="stub", status="succeeded").inc()
        payments_succeeded_total.labels(kind="stub").inc()
        payments_amount_total_kopecks.inc(amount_kopecks)

        logger.info(
            "[STUB] Платёж %s на %s коп. сразу зачислен user_tg_id=%s (баланс: %s → %s)",
            payment_id_str,
            amount_kopecks,
            tg_id,
            user.balance - amount_kopecks,
            user.balance,
        )

        return {
            "payment_id": payment_id_str,
            "payment_url": f"https://stub.local/pay/{payment_id_str}",
            "qr_code": "",
            "amount_rubles": amount_rubles,
            "status": "succeeded",
        }

    # Создаем платеж через ЮKassa
    try:
        payment_data = await create_sbp_payment(
            amount_kopecks=amount_kopecks,
            user_tg_id=tg_id,
            description=f"Пополнение баланса OnyxVpn (user {tg_id})",
        )
    except YooKassaPaymentError as e:
        logger.error("Ошибка создания платежа: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось создать платеж",
        ) from e

    # Сохраняем платеж в БД со статусом pending
    payment = Payment(
        user_id=user.id,
        amount=amount_kopecks,
        payment_id=payment_data["payment_id"],
        status=PaymentStatus.PENDING,
    )
    session.add(payment)
    await session.commit()

    logger.info(
        "Создан платеж %s на %s копеек для user_tg_id=%s",
        payment_data["payment_id"],
        amount_kopecks,
        tg_id,
    )

    return {
        "payment_id": payment_data["payment_id"],
        "payment_url": payment_data["confirmation_url"],
        "qr_code": payment_data["qr_code"],
        "amount_rubles": payment_data["amount_rubles"],
        "status": payment_data["status"],
    }


@router.get("/payment/status")
async def get_payment_status(
    tg_id: int = Depends(get_current_user_tg_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Статус последнего ожидающего платежа пользователя.

    Используется фронтом для polling во время СБП-оплаты:
    BalanceScreen и TopUpBottomSheet опрашивают эндпоинт каждые ~2с,
    пока не получат status="succeeded" — это значит, что webhook от ЮKassa
    уже зачислил баланс, и UI можно закрывать.

    Returns:
        - status="pending"   — есть незавершённый платёж, опрашиваем дальше
        - status="succeeded" — последний платёж успешно завершён (баланс уже пополнен)
        - status="none"      — нет платежей (пользователь ещё не начинал оплату)
        - status="canceled"  — последний платёж отменён (пользователь закрыл СБП-форму)

    Источник правды — локальная БД, обновляемая webhook'ом. Запросы к API ЮKassa
    отсюда не делаем — это лишний round-trip и rate-limit.
    """
    user_q = select(User).where(User.tg_id == tg_id)
    user = (await session.execute(user_q)).scalar_one_or_none()

    if not user:
        return {"status": "none", "payment_id": None}

    pay_q = (
        select(Payment)
        .where(Payment.user_id == user.id)
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    payment = (await session.execute(pay_q)).scalar_one_or_none()

    if not payment:
        return {"status": "none", "payment_id": None}

    return {
        "status": payment.status,
        "payment_id": payment.payment_id,
        "amount_rubles": payment.amount / 100,
    }


@router.post("/payment/webhook")
async def payment_webhook(
    payload: YooKassaWebhookPayload,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Обработать webhook от ЮKassa.

    Защита:
    - IP whitelist — только официальные IP ЮKassa.
    - amount и user_id НЕ берутся из payload'а — берём из нашей записи Payment,
      созданной в /payment/create. Это исключает подделку суммы/получателя.
    - payment_status валидируется по фиксированному списку.
    - Зачисление баланса — только при первом переходе в succeeded.
    """
    await verify_yookassa_ip(request)

    # Pydantic уже проверил, что payment_id и status — непустые строки.
    payment_id = payload.payment_id
    raw_status = payload.status

    # Конвертируем строку в PaymentStatus, чтобы дальше работать с типизированным enum.
    try:
        payment_status = PaymentStatus(raw_status)
    except ValueError:
        logger.warning(
            "Webhook с неизвестным status=%s для payment_id=%s",
            raw_status,
            payment_id,
        )
        payment_webhook_rejected_total.labels(reason="unknown_status").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недопустимый статус платежа: {raw_status}",
        )

    # Ищем нашу запись Payment с блокировкой строки (SELECT FOR UPDATE).
    # amount и user_id берём отсюда — payload им не доверяем.
    # with_for_update() сериализует параллельные webhook'и для одного payment_id:
    # без блокировки два retry от ЮKassa прошли бы проверку идемпотентности
    # одновременно и зачислили баланс дважды.
    payment_q = (
        select(Payment)
        .where(Payment.payment_id == payment_id)
        .with_for_update()
    )
    payment = (await session.execute(payment_q)).scalar_one_or_none()

    if not payment:
        # Webhook для платежа, которого нет в нашей БД — отвергаем.
        # Это защищает от подделки payment_id для начисления на чужой аккаунт.
        logger.warning("Webhook для неизвестного payment_id: %s", payment_id)
        payment_webhook_rejected_total.labels(reason="unknown_payment").inc()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Платёж не найден",
        )

    # Идемпотентность + защита от отката:
    # 1. Если уже succeeded — не откатываем в canceled и не зачисляем повторно.
    # 2. Если уже canceled и пришёл не succeeded — no-op.
    #    (canceled → succeeded допускаем: пользователь мог отменить и оплатить заново.)
    if payment.status == PaymentStatus.SUCCEEDED:
        return {"message": "Already processed"}
    if payment.status == PaymentStatus.CANCELED and payment_status != PaymentStatus.SUCCEEDED:
        return {"message": "Already canceled"}

    payment.status = payment_status

    # Зачисляем баланс ТОЛЬКО при переходе в succeeded.
    if payment_status == PaymentStatus.SUCCEEDED:
        # Лочим и User: два параллельных webhook'а для разных платежей одного
        # юзера не должны потерять обновление баланса.
        user_q = (
            select(User)
            .where(User.id == payment.user_id)
            .with_for_update()
        )
        user = (await session.execute(user_q)).scalar_one()
        user.balance += payment.amount
        # Webhook всегда приходит от YooKassa → kind="real".
        # payments_amount_total_kopecks — source of truth для revenue.
        payments_succeeded_total.labels(kind="real").inc()
        payments_amount_total_kopecks.inc(payment.amount)
        logger.info(
            "Начислено %s коп. пользователю tg_id=%s через payment_id=%s",
            payment.amount,
            user.tg_id,
            payment_id,
        )

    await session.commit()

    return {"message": "Webhook processed"}
