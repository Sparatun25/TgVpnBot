"""Шифрование connection_url (Fernet, симметричный AES-128 + HMAC-SHA256).

В проде ОБЯЗАТЕЛЬНО задать DB_ENCRYPTION_KEY (Fernet-ключ, 44 символа base64).
Без ключа — connection_url хранится в БД plaintext (dev-режим, обратная совместимость).

Генерация ключа:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Ротация ключей:
    Текущая версия кода поддерживает только один ключ. Для ротации нужно
    расшифровать все значения старым ключом и зашифровать новым — отдельной
    миграцией (ALTER TABLE ... или скриптом Python).
"""

import logging

from cryptography.fernet import Fernet, InvalidToken

from core.config import settings

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet | None:
    """Возвращает Fernet или None, если ключ не настроен (dev-режим)."""
    key = settings.db_encryption_key
    if key is None:
        return None
    # pydantic SecretStr хранит значение в .get_secret_value(), не в самом str.
    raw_key = key.get_secret_value()
    if not raw_key:
        return None
    return Fernet(raw_key.encode("ascii"))


def encrypt_connection_url(plaintext: str) -> str:
    """Зашифровать connection_url перед записью в БД.

    Если ключ не настроен — возвращает plaintext (для обратной совместимости).
    Иначе возвращает base64-токен Fernet.
    """
    fernet = _get_fernet()
    if fernet is None:
        return plaintext
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_connection_url(stored: str) -> str:
    """Расшифровать connection_url при чтении из БД.

    Если ключ не настроен — возвращает значение как есть.
    Если значение похоже на Fernet-токен, но ключ не подходит (ротация или
    повреждение) — логируем warning и возвращаем как есть. Это безопаснее,
    чем ронять приложение на каждом чтении из-за миграции.
    Если значение НЕ Fernet-токен (legacy plaintext) — возвращаем как есть.
    """
    fernet = _get_fernet()
    if fernet is None:
        return stored

    # Fernet-токены начинаются с версионного байта 'g' (gAAAAA...).
    # Это эвристика для отличия от plaintext (vpn://...).
    if not stored.startswith("gAAAAA"):
        return stored

    try:
        return fernet.decrypt(stored.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.warning(
            "Не удалось расшифровать connection_url — возможно, ключ ротирован. "
            "Возвращаем значение as-is.",
        )
        return stored
