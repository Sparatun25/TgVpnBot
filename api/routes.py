"""API роуты для Mini App."""

import hashlib
import hmac
import ipaddress
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user_tg_id
from core.config import settings
from core.db import get_session
from database.models import Payment, Subscription, User
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


@router.get("/profile")
async def get_profile(
    tg_id: int = Depends(get_current_user_tg_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Получить профиль пользователя.

    Возвращает баланс, статус подписки и ссылку на ключ.
    """
    # Ищем пользователя
    query = select(User).where(User.tg_id == tg_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    # Ищем активную подписку
    now = datetime.now(timezone.utc)
    sub_query = select(Subscription).where(
        Subscription.user_id == user.id,
        Subscription.is_active == True,
        Subscription.expires_at > now,
    )
    sub_result = await session.execute(sub_query)
    active_sub = sub_result.scalar_one_or_none()

    # Проверяем, использовал ли пользователь триал когда-либо
    trial_query = select(Subscription).where(
        Subscription.user_id == user.id,
        Subscription.plan_type == "trial",
    )
    trial_result = await session.execute(trial_query)
    has_used_trial = trial_result.scalar_one_or_none() is not None

    return {
        "balance": user.balance,
        "referral_code": user.referral_code,
        "subscription": {
            "active": active_sub is not None,
            "plan_type": active_sub.plan_type if active_sub else None,
            "expires_at": active_sub.expires_at.isoformat() if active_sub else None,
            "connection_url": active_sub.connection_url if active_sub else None,
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
    # Ищем пользователя
    query = select(User).where(User.tg_id == tg_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        # Создаём нового пользователя
        user = User(tg_id=tg_id)
        session.add(user)
        await session.flush()

    # Проверяем, есть ли уже триал
    trial_query = select(Subscription).where(
        Subscription.user_id == user.id,
        Subscription.plan_type == "trial",
    )
    trial_result = await session.execute(trial_query)
    existing_trial = trial_result.scalar_one_or_none()

    if existing_trial:
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Уже есть активная подписка",
        )

    # Генерируем ключ Amnezia
    try:
        connection_url, client_pub_key = await create_client_key(user.id, is_trial=True)
    except RuntimeError as e:
        logger.error("Ошибка создания ключа Amnezia: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось создать VPN-ключ",
        ) from e

    # Создаём подписку
    expires_at = now + timedelta(days=3)
    subscription = Subscription(
        user_id=user.id,
        uuid=client_pub_key,  # Сохраняем public key для отзыва ключа
        plan_type="trial",
        expires_at=expires_at,
        is_active=True,
        connection_url=connection_url,
    )
    session.add(subscription)

    # Устанавливаем время создания ключа для отслеживания неактивных
    user.key_created_at = now

    await session.commit()

    return {
        "message": "Триал активирован",
        "expires_at": expires_at.isoformat(),
        "connection_url": connection_url,
    }


@router.post("/subscription/purchase")
async def purchase_subscription(
    payload: dict,
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
    tariff_id = payload.get("tariff_id")

    if not tariff_id or tariff_id not in TARIFFS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный тариф",
        )

    tariff = TARIFFS[tariff_id]
    price = tariff["price_kopecks"]
    days = tariff["days"]

    # Ищем пользователя
    query = select(User).where(User.tg_id == tg_id)
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
        active_sub.plan_type = tariff_id

        # Генерируем новый ключ (старый может быть скомпрометирован)
        try:
            connection_url, client_pub_key = await create_client_key(user.id, is_trial=False)
            active_sub.uuid = client_pub_key
            active_sub.connection_url = connection_url
        except RuntimeError as e:
            logger.error("Ошибка создания ключа Amnezia: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Не удалось создать VPN-ключ",
            ) from e

        subscription = active_sub
        action = "продлена"
    else:
        # Создаём новую подписку
        # Генерируем ключ Amnezia
        try:
            connection_url, client_pub_key = await create_client_key(user.id, is_trial=False)
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
            plan_type=tariff_id,
            expires_at=expires_at,
            is_active=True,
            connection_url=connection_url,
        )
        session.add(subscription)
        action = "активирована"

    # Списываем деньги
    user.balance -= price

    await session.commit()

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
        "connection_url": subscription.connection_url,
        "plan_type": subscription.plan_type,
        "balance_remaining": user.balance,
    }


@router.post("/payment/create")
async def create_payment(
    payload: dict,
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
    amount_kopecks = payload.get("amount_kopecks")

    if not amount_kopecks or amount_kopecks <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректная сумма",
        )

    # Валидация: сумма от 10 рублей (1000 копеек) до 100 000 рублей
    if amount_kopecks < 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Минимальная сумма пополнения: 10 рублей",
        )

    if amount_kopecks > 10_000_000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Максимальная сумма пополнения: 100 000 рублей",
        )

    # Проверяем, что пользователь существует
    query = select(User).where(User.tg_id == tg_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

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
        status="pending",
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


@router.post("/payment/webhook")
async def payment_webhook(
    payload: dict,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Обработать webhook от ЮKassa.

    Защищён IP whitelist — принимает запросы только с официальных IP ЮKassa.
    """
    # Проверяем IP-адрес отправителя
    await verify_yookassa_ip(request)

    payment_id = payload.get("payment_id")
    user_tg_id = payload.get("user_tg_id")
    amount = payload.get("amount")
    payment_status = payload.get("status")

    if not all([payment_id, user_tg_id, amount, payment_status]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный payload",
        )

    # Проверяем уникальность payment_id
    existing_query = select(Payment).where(Payment.payment_id == payment_id)
    existing_result = await session.execute(existing_query)
    existing = existing_result.scalar_one_or_none()

    if existing:
        logger.warning("Дублирующийся payment_id: %s", payment_id)
        return {"message": "Payment already processed"}

    # Ищем пользователя
    user_query = select(User).where(User.tg_id == user_tg_id)
    user_result = await session.execute(user_query)
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    # Создаём запись платежа
    payment = Payment(
        user_id=user.id,
        amount=amount,
        payment_id=payment_id,
        status=payment_status,
    )
    session.add(payment)

    # Если платёж успешный — начисляем баланс
    if payment_status == "success":
        user.balance += amount
        logger.info(
            "Начислено %s копеек пользователю tg_id=%s",
            amount,
            user_tg_id,
        )

    await session.commit()

    return {"message": "Webhook processed"}
