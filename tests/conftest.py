"""Общие фикстуры и хелперы для всех тестов проекта.

Здесь лежит всё, что переиспользуется между test_crypto.py, test_auth.py
и будущими тестами: детерминированный bot_token, фикстуры для подмены
settings.*, билдеры валидных initData и Login Widget payload'ов.
"""

# ─────────────────────────────────────────────────────────
# Подготовка окружения ДО импорта core.config.
# core.config.Settings требует обязательные bot_token и database_url —
# без них pydantic падает на инстанцировании Settings(), и ВСЕ тесты
# валятся на этапе collection. setdefault: если переменные уже заданы
# в окружении (CI, локально с экспортированными значениями) — не трогаем.
# ─────────────────────────────────────────────────────────
import os

os.environ.setdefault("BOT_TOKEN", "test_bot_token_for_collection_only")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)

import hashlib
import hmac
import time

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from core.config import settings


# Детерминированный токен для тестов. Не настоящий — только для HMAC-вычислений.
TEST_BOT_TOKEN = "test_bot_token_for_unit_tests_do_not_use_in_production"


@pytest.fixture
def fernet_key() -> str:
    """Свежий Fernet-ключ для каждого теста (изоляция между тестами)."""
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def patched_db_encryption_key(monkeypatch, fernet_key: str) -> str:
    """Подменяет settings.db_encryption_key на свежий Fernet-ключ.

    Без этого фикстура encrypt_connection_url вернёт plaintext (fallback),
    что меняет поведение большинства тестов crypto.
    """
    monkeypatch.setattr(settings, "db_encryption_key", SecretStr(fernet_key))
    return fernet_key


@pytest.fixture
def patched_bot_token(monkeypatch) -> str:
    """Подменяет settings.bot_token на детерминированный TEST_BOT_TOKEN.

    Тесты auth.py рассчитывают HMAC по этому токену. Патчим через
    SecretStr, потому что settings.bot_token — типизированное поле.
    """
    monkeypatch.setattr(settings, "bot_token", SecretStr(TEST_BOT_TOKEN))
    return TEST_BOT_TOKEN


def build_init_data(
    bot_token: str,
    *,
    auth_date: int | None = None,
    user_id: int = 123456,
    first_name: str = "Test",
) -> str:
    """Собрать валидный initData (как отправляет Telegram WebApp).

    Структура: query string с полями auth_date, user (JSON-строка), hash.
    hash считается по алгоритму Telegram: HMAC-SHA256 от data_check_string
    с ключом HMAC-SHA256("WebAppData", bot_token).
    """
    if auth_date is None:
        auth_date = int(time.time())

    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    user_json = f'{{"id": {user_id}, "first_name": "{first_name}"}}'
    data_check_string = f"auth_date={auth_date}\nuser={user_json}"
    check_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return f"auth_date={auth_date}&user={user_json}&hash={check_hash}"


def build_login_widget_data(
    bot_token: str,
    *,
    auth_date: int | None = None,
    user_id: int = 123456,
    first_name: str = "Test",
    username: str = "testuser",
) -> dict[str, str]:
    """Собрать валидный payload Telegram Login Widget (все поля — строки).

    Возвращает dict (не query string), потому что Login Widget отдаёт
    JSON-объект, который фронт потом мапит в headers.
    hash считается по алгоритму Telegram: HMAC-SHA256 от data_check_string
    с ключом SHA256(bot_token) — другой, чем у initData!
    """
    if auth_date is None:
        auth_date = int(time.time())

    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()

    fields: dict[str, str] = {
        "id": str(user_id),
        "first_name": first_name,
        "username": username,
        "auth_date": str(auth_date),
    }

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    check_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    fields["hash"] = check_hash
    return fields
