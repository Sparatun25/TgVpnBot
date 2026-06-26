"""Валидация Telegram WebApp initData и Login Widget.

CSRF (S14): приложение использует Bearer-токены в Authorization header.
Браузер НЕ отправляет их автоматически — злоумышленник не может заставить
пользователя выполнить авторизованный запрос с другого origin. Классические
CSRF-атаки (с использованием cookies) здесь неприменимы.

HTTPS (S12): в production TLS терминируется на nginx. За reverse-proxy
backend работает по HTTP, но прокси передаёт X-Forwarded-Proto=https, и
SecurityHeadersMiddleware добавляет Strict-Transport-Security (см. api/main.py).
Локальная разработка — http://localhost:8000, HSTS не активируется.
"""

import hashlib
import hmac
import logging
import time
from urllib.parse import parse_qsl

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

# Replay-protection: initData от Telegram WebApp действителен не дольше 5 минут
# после подписания. Стандартная рекомендация Telegram, защищает от перехвата.
MAX_INIT_DATA_AGE_SECONDS = 300

# Допустимое расхождение часов между клиентом и сервером (часы могут отставать/спешить).
CLOCK_SKEW_TOLERANCE_SECONDS = 60


def _validate_init_data(init_data: str, bot_token: str) -> dict[str, str]:
    """
    Валидировать initData от Telegram WebApp.

    Алгоритм:
    1. Парсим initData в словарь.
    2. Извлекаем hash.
    3. Проверяем auth_date — не старше MAX_INIT_DATA_AGE_SECONDS.
       Это защита от replay-атак: перехваченный initData становится
       бесполезен через 5 минут после подписания Telegram'ом.
    4. Считаем secret_key = HMAC-SHA256("WebAppData", bot_token).
    5. Сортируем пары по ключу, склеиваем через \n.
    6. Считаем check_hash = HMAC-SHA256(data_check_string, secret_key).
    7. Сравниваем с переданным hash.

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

    # Replay-protection: auth_date должен быть недавним.
    auth_date_raw = parsed.get("auth_date")
    if not auth_date_raw:
        raise ValueError("Отсутствует auth_date в initData")
    try:
        auth_date = int(auth_date_raw)
    except (TypeError, ValueError) as e:
        raise ValueError("Некорректный auth_date в initData") from e
    current_time = int(time.time())
    if current_time - auth_date > MAX_INIT_DATA_AGE_SECONDS:
        raise ValueError("auth_date устарел (возможна replay-атака)")
    if auth_date > current_time + CLOCK_SKEW_TOLERANCE_SECONDS:
        raise ValueError("auth_date из будущего (возможна подделка)")

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

    bot_token = settings.bot_token

    if not bot_token:
        logger.error("BOT_TOKEN не настроен")
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


def validate_login_widget(data: dict[str, str], bot_token: str) -> int:
    """
    Валидировать данные от Telegram Login Widget.

    Алгоритм:
    1. Проверяем наличие обязательных полей (id, first_name, last_name, username, photo_url, auth_date, hash).
    2. Проверяем, что auth_date не устарел (не старше 5 минут).
    3. Считаем secret_key = SHA256(bot_token).
    4. Сортируем все поля кроме hash, склеиваем в строку.
    5. Считаем HMAC-SHA256 этой строки с secret_key.
    6. Сравниваем с hash.

    Returns:
        Telegram ID пользователя.

    Raises:
        ValueError: Если валидация не прошла.
    """
    # Обязательные поля
    required_fields = ["id", "auth_date", "hash"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Отсутствует поле {field}")

    # Проверяем, что auth_date не устарел (5 минут)
    auth_date = int(data["auth_date"])
    current_time = int(time.time())
    if current_time - auth_date > 300:  # 5 минут
        raise ValueError("auth_date устарел")

    # Извлекаем hash. Копируем dict, чтобы не мутировать входной словарь
    # caller'а — иначе неожиданный side effect для всех, кто передаёт
    # сюда ссылку на свой dict.
    data = dict(data)
    received_hash = data.pop("hash")

    # Считаем secret_key = SHA256(bot_token)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()

    # Сортируем все поля кроме hash и склеиваем
    sorted_pairs = sorted(data.items(), key=lambda x: x[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_pairs)

    # Считаем HMAC-SHA256
    check_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Сравниваем
    if not hmac.compare_digest(check_hash, received_hash):
        raise ValueError("Неверный hash Login Widget")

    return int(data["id"])
