"""Интеграция с ЮKassa для платежей через СБП."""

import logging
import uuid
from typing import Any

import aiohttp

from core.config import settings

logger = logging.getLogger(__name__)

# ЮKassa API endpoints
YUKASSA_API_URL = "https://api.yookassa.ru/v3"


class YooKassaPaymentError(Exception):
    """Ошибка при создании платежа в ЮKassa."""

    pass


async def create_sbp_payment(
    amount_kopecks: int,
    user_tg_id: int,
    description: str | None = None,
) -> dict[str, Any]:
    """
    Создать платеж через СБП (ЮKassa).

    Args:
        amount_kopecks: Сумма платежа в копейках.
        user_tg_id: Telegram ID пользователя.
        description: Описание платежа (опционально).

    Returns:
        Словарь с данными платежа:
        {
            "payment_id": str,  # ID платежа в ЮKassa
            "confirmation_url": str,  # URL для подтверждения/оплаты
            "qr_code": str,  # Base64-encoded QR-код для СБП
            "amount_rubles": float,  # Сумма в рублях
            "status": str,  # Статус платежа
        }

    Raises:
        YooKassaPaymentError: Если не удалось создать платеж.
    """
    if not settings.yukassa_shop_id or not settings.yukassa_secret_key:
        raise YooKassaPaymentError("ЮKassa не настроена")

    # Конвертируем копейки в рубли
    amount_rubles = amount_kopecks / 100

    # Уникальный ID платежа (idempotency key)
    idempotence_key = str(uuid.uuid4())

    # Payload для ЮKassa
    payload = {
        "amount": {
            "value": f"{amount_rubles:.2f}",
            "currency": "RUB",
        },
        "confirmation": {
            "type": "qr",
            "locale": "ru_RU",
        },
        "description": description or f"Пополнение баланса OnyxVpn (user {user_tg_id})",
        "metadata": {
            "user_tg_id": user_tg_id,
        },
    }

    headers = {
        "Idempotence-Key": idempotence_key,
        "Content-Type": "application/json",
    }

    logger.info(
        "Создание платежа ЮKassa: %s руб. для user_tg_id=%s",
        amount_rubles,
        user_tg_id,
    )

    try:
        async with aiohttp.ClientSession() as session:
            # Базовая аутентификация: shop_id:secret_key
            auth = aiohttp.BasicAuth(
                login=settings.yukassa_shop_id,
                password=settings.yukassa_secret_key.get_secret_value(),
            )

            async with session.post(
                f"{YUKASSA_API_URL}/payments",
                json=payload,
                headers=headers,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        "Ошибка создания платежа ЮKassa: status=%s, body=%s",
                        response.status,
                        error_text,
                    )
                    raise YooKassaPaymentError(
                        f"ЮKassa вернула ошибку: {response.status}"
                    )

                data = await response.json()

                # Извлекаем данные платежа
                payment_id = data.get("id")
                confirmation = data.get("confirmation", {})
                confirmation_url = confirmation.get("confirmation_url")
                qr_code = confirmation.get("confirmation_data")
                status = data.get("status")

                if not payment_id:
                    raise YooKassaPaymentError("ЮKassa не вернула payment_id")

                logger.info(
                    "Платеж создан: payment_id=%s, status=%s",
                    payment_id,
                    status,
                )

                return {
                    "payment_id": payment_id,
                    "confirmation_url": confirmation_url,
                    "qr_code": qr_code,
                    "amount_rubles": amount_rubles,
                    "status": status,
                }

    except aiohttp.ClientError as e:
        logger.error("Ошибка соединения с ЮKassa: %s", e)
        raise YooKassaPaymentError(f"Ошибка соединения: {e}") from e

    except Exception as e:
        logger.exception("Неожиданная ошибка при создании платежа: %s", e)
        raise YooKassaPaymentError(f"Неожиданная ошибка: {e}") from e


async def get_payment_status(payment_id: str) -> dict[str, Any]:
    """
    Получить статус платежа из ЮKassa.

    Args:
        payment_id: ID платежа в ЮKassa.

    Returns:
        Словарь с данными платежа:
        {
            "payment_id": str,
            "status": str,  # pending, waiting_for_capture, succeeded, canceled
            "amount_rubles": float,
            "paid": bool,
        }

    Raises:
        YooKassaPaymentError: Если не удалось получить статус.
    """
    if not settings.yukassa_shop_id or not settings.yukassa_secret_key:
        raise YooKassaPaymentError("ЮKassa не настроена")

    try:
        async with aiohttp.ClientSession() as session:
            auth = aiohttp.BasicAuth(
                login=settings.yukassa_shop_id,
                password=settings.yukassa_secret_key.get_secret_value(),
            )

            async with session.get(
                f"{YUKASSA_API_URL}/payments/{payment_id}",
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        "Ошибка получения статуса платежа: status=%s, body=%s",
                        response.status,
                        error_text,
                    )
                    raise YooKassaPaymentError(
                        f"ЮKassa вернула ошибку: {response.status}"
                    )

                data = await response.json()

                amount_value = float(data.get("amount", {}).get("value", 0))
                status = data.get("status")
                paid = data.get("paid", False)

                return {
                    "payment_id": payment_id,
                    "status": status,
                    "amount_rubles": amount_value,
                    "paid": paid,
                }

    except aiohttp.ClientError as e:
        logger.error("Ошибка соединения с ЮKassa: %s", e)
        raise YooKassaPaymentError(f"Ошибка соединения: {e}") from e

    except Exception as e:
        logger.exception("Неожиданная ошибка при получении статуса: %s", e)
        raise YooKassaPaymentError(f"Неожиданная ошибка: {e}") from e
