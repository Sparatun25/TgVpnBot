"""Валидация Telegram WebApp initData."""

import hashlib
import hmac
import logging
from urllib.parse import parse_qsl

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


def _validate_init_data(init_data: str, bot_token: str) -> dict[str, str]:
    """
    Валидировать initData от Telegram WebApp.

    Алгоритм:
    1. Парсим initData в словарь.
    2. Извлекаем hash.
    3. Считаем secret_key = HMAC-SHA256("WebAppData", bot_token).
    4. Сортируем пары по ключу, склеиваем через \n.
    5. Считаем check_hash = HMAC-SHA256(data_check_string, secret_key).
    6. Сравниваем с переданным hash.

    Returns:
        Словарь распарсенных данных.

    Raises:
        ValueError: Если валидация не прошла.
    """
    if not init_data:
        raise ValueError("Пустой initData")

    # Парсим строку в словарь
    parsed = dict(parse_qsl(init_data))

    # Извлекаем hash
    received_hash = parsed.pop("hash", None)

    if not received_hash:
        raise ValueError("Отсутствует hash в initData")

    # Считаем secret_key
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    # Сортируем пары по ключу и склеиваем
    sorted_pairs = sorted(parsed.items(), key=lambda x: x[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_pairs)

    # Считаем check_hash
    check_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Сравниваем
    if not hmac.compare_digest(check_hash, received_hash):
        raise ValueError("Неверный hash initData")

    return parsed


def _extract_tg_id(parsed_data: dict[str, str]) -> int:
    """
    Извлечь tg_id из распарсенных данных initData.

    Поле user содержит JSON-строку с данными пользователя.
    """
    import json

    user_json = parsed_data.get("user")

    if not user_json:
        raise ValueError("Отсутствует поле user в initData")

    try:
        user_data = json.loads(user_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Некорректный JSON в поле user: {e}") from e

    tg_id = user_data.get("id")

    if not tg_id:
        raise ValueError("Отсутствует id в поле user")

    return int(tg_id)


async def get_current_user_tg_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> int:
    """
    Зависимость FastAPI для получения tg_id из initData.

    Ожидает заголовок Authorization: Bearer <initData>.

    Returns:
        Telegram ID пользователя.

    Raises:
        HTTPException 401: Если валидация не прошла.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Отсутствует токен авторизации",
        )

    init_data = credentials.credentials

    bot_token = settings.telegram_bot_token

    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN не настроен")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Серверная ошибка конфигурации",
        )

    try:
        parsed = _validate_init_data(init_data, bot_token.get_secret_value())
        tg_id = _extract_tg_id(parsed)
    except ValueError as e:
        logger.warning("Ошибка валидации initData: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен авторизации",
        ) from e

    return tg_id
