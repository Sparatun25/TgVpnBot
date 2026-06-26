"""Тесты для core/crypto.py — Fernet-шифрование connection_url.

Покрывает:
- encrypt/decrypt roundtrip с ключом
- Fallback на plaintext когда ключ не задан (dev-режим)
- Эвристику Fernet-токена: plaintext-значения не пытаемся дешифровать
- Устойчивость к неправильному ключу (ротация) — возвращаем as-is + warning
- Unicode и граничные случаи (пустая строка)
"""

from cryptography.fernet import Fernet
from pydantic import SecretStr

from core.config import settings
from core.crypto import decrypt_connection_url, encrypt_connection_url


class TestFernetEncryption:
    """encrypt/decrypt с настроенным DB_ENCRYPTION_KEY."""

    def test_encrypt_returns_fernet_format(self, patched_db_encryption_key):
        # Fernet-токены начинаются с версионного байта 0x80, в base64 это "gAAAAA".
        result = encrypt_connection_url("vpn://secret-key")
        assert result.startswith("gAAAAA"), (
            f"Ожидался Fernet-токен, получили {result[:20]!r}"
        )

    def test_encrypt_changes_each_call(
        self, patched_db_encryption_key
    ):
        # Fernet использует случайный IV, поэтому два encrypt одного и того же
        # plaintext дают разные токены. Это норма для Fernet.
        a = encrypt_connection_url("same")
        b = encrypt_connection_url("same")
        assert a != b

    def test_roundtrip_returns_original(self, patched_db_encryption_key):
        original = "vpn://some-secret-connection-string"
        assert decrypt_connection_url(encrypt_connection_url(original)) == original

    def test_roundtrip_unicode(self, patched_db_encryption_key):
        # VPN-ключи и метаданные теоретически могут содержать эмодзи/кириллицу
        # (имя кота-талисмана в description). Fernet работает с байтами, но
        # убедимся, что наш wrapper не теряет ничего при encode/decode.
        original = "vpn://🦀-кот-защитник-🔐"
        assert decrypt_connection_url(encrypt_connection_url(original)) == original

    def test_roundtrip_empty_string(self, patched_db_encryption_key):
        # Граничный случай: пустая строка — должна корректно roundtrip'иться,
        # а не падать на encode/decode.
        assert decrypt_connection_url(encrypt_connection_url("")) == ""

    def test_roundtrip_long_string(self, patched_db_encryption_key):
        # vpn:// ключи Amnezia содержат zlib-сжатый JSON конфига (~500-1000 байт).
        # Проверим, что длинные значения не ломаются.
        original = "vpn://" + "x" * 4096
        assert decrypt_connection_url(encrypt_connection_url(original)) == original

    def test_decrypt_plaintext_returns_as_is(self, patched_db_encryption_key):
        # Если в БД остались plaintext-значения от старой версии (миграция
        # без шифрования) — decrypt не должен пытаться их дешифровать.
        # Эвристика: Fernet-токен всегда начинается с "gAAAAA".
        plaintext = "vpn://legacy-plaintext-data"
        assert decrypt_connection_url(plaintext) == plaintext

    def test_decrypt_non_fernet_garbage_returns_as_is(
        self, patched_db_encryption_key
    ):
        # Любая строка, не похожая на Fernet-токен, возвращается как есть —
        # иначе ротация ключей или повреждение данных ломали бы всё.
        assert decrypt_connection_url("not-a-fernet-token") == "not-a-fernet-token"

    def test_decrypt_with_wrong_key_returns_as_is(self, monkeypatch):
        # Шифруем одним ключом, пробуем расшифровать другим. Fernet бросит
        # InvalidToken, наш wrapper должен вернуть зашифрованное значение
        # as-is (с warning в логах) — лучше показать клиенту старый
        # vpn:// чем уронить приложение на каждом чтении.
        encrypt_key = Fernet.generate_key().decode()
        monkeypatch.setattr(
            settings, "db_encryption_key", SecretStr(encrypt_key)
        )
        encrypted = encrypt_connection_url("secret")

        decrypt_key = Fernet.generate_key().decode()
        monkeypatch.setattr(
            settings, "db_encryption_key", SecretStr(decrypt_key)
        )

        assert decrypt_connection_url(encrypted) == encrypted


class TestNoKeyFallback:
    """Поведение без DB_ENCRYPTION_KEY (dev-режим)."""

    def test_encrypt_returns_plaintext(self, monkeypatch):
        # Явно обнуляем ключ, чтобы тест не зависел от .env.
        monkeypatch.setattr(settings, "db_encryption_key", None)
        plaintext = "vpn://secret-key"
        assert encrypt_connection_url(plaintext) == plaintext

    def test_decrypt_returns_stored_as_is(self, monkeypatch):
        monkeypatch.setattr(settings, "db_encryption_key", None)
        # Любое значение (Fernet-токен, plaintext, пустая строка) возвращается
        # как есть — без ключа мы физически не можем расшифровать.
        assert decrypt_connection_url("anything") == "anything"
        assert decrypt_connection_url("vpn://secret") == "vpn://secret"
        assert decrypt_connection_url("gAAAAA-fake-token") == "gAAAAA-fake-token"
        assert decrypt_connection_url("") == ""
