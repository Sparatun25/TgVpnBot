"""Тесты для api/auth.py — валидация Telegram WebApp initData и Login Widget.

Покрывает:
- _validate_init_data: все ветки replay-protection, проверки hash, неверный токен
- _extract_tg_id: парсинг user JSON, защита от мусорных значений
- validate_login_widget: тот же набор + инвариант «не мутировать input»

Все HMAC-значения считаются в conftest.py (build_init_data / build_login_widget_data)
с детерминированным TEST_BOT_TOKEN, который подменяется в settings через фикстуру
patched_bot_token.
"""

import time

import pytest

from api.auth import _extract_tg_id, _validate_init_data, validate_login_widget
from tests.conftest import (
    TEST_BOT_TOKEN,
    build_init_data,
    build_login_widget_data,
)


# ─────────────────────────────────────────────────────────
# _validate_init_data (Telegram WebApp)
# ─────────────────────────────────────────────────────────


class TestValidateInitData:
    """_validate_init_data: валидация подписи initData от Telegram WebApp."""

    def test_valid_returns_parsed_dict(self, patched_bot_token):
        init_data = build_init_data(TEST_BOT_TOKEN)
        result = _validate_init_data(init_data, TEST_BOT_TOKEN)
        assert isinstance(result, dict)
        assert "auth_date" in result
        assert "user" in result

    def test_empty_string_raises(self, patched_bot_token):
        with pytest.raises(ValueError, match="Пустой"):
            _validate_init_data("", TEST_BOT_TOKEN)

    def test_no_hash_raises(self, patched_bot_token):
        with pytest.raises(ValueError, match="hash"):
            _validate_init_data("auth_date=123&user=abc", TEST_BOT_TOKEN)

    def test_no_auth_date_raises(self, patched_bot_token):
        # hash есть, но auth_date отсутствует — replay-protection не сможет работать.
        with pytest.raises(ValueError, match="auth_date"):
            _validate_init_data("hash=abc", TEST_BOT_TOKEN)

    def test_invalid_auth_date_format_raises(self, patched_bot_token):
        # auth_date должен парситься в int. Не-числовая строка → ValueError.
        with pytest.raises(ValueError, match="auth_date"):
            _validate_init_data(
                "auth_date=not_a_number&hash=abc",
                TEST_BOT_TOKEN,
            )

    def test_expired_auth_date_raises(self, patched_bot_token, monkeypatch):
        # Подкручиваем «настоящее» время на 10 минут вперёд, чтобы валидный
        # на момент подписания initData оказался «просрочен» (>5 минут).
        real_auth_date = int(time.time())
        monkeypatch.setattr("time.time", lambda: real_auth_date + 600)
        init_data = build_init_data(TEST_BOT_TOKEN, auth_date=real_auth_date)
        with pytest.raises(ValueError, match="устарел"):
            _validate_init_data(init_data, TEST_BOT_TOKEN)

    def test_future_auth_date_raises(self, patched_bot_token, monkeypatch):
        # auth_date на 10 минут в будущем относительно «настоящего» времени —
        # возможная подделка при расхождении часов.
        now = int(time.time())
        future_auth_date = now + 600
        monkeypatch.setattr("time.time", lambda: now)
        init_data = build_init_data(TEST_BOT_TOKEN, auth_date=future_auth_date)
        with pytest.raises(ValueError, match="будущего"):
            _validate_init_data(init_data, TEST_BOT_TOKEN)

    def test_invalid_hash_raises(self, patched_bot_token):
        init_data = build_init_data(TEST_BOT_TOKEN)
        # Заменяем реальный hash на 64 hex-символа мусора.
        parts = init_data.split("hash=")
        tampered = f"{parts[0]}hash={'d' * 64}"
        with pytest.raises(ValueError, match="hash"):
            _validate_init_data(tampered, TEST_BOT_TOKEN)

    def test_wrong_bot_token_raises(self, patched_bot_token):
        # initData подписан TEST_BOT_TOKEN, проверяем с другим токеном —
        # HMAC не совпадёт.
        init_data = build_init_data(TEST_BOT_TOKEN)
        with pytest.raises(ValueError, match="hash"):
            _validate_init_data(init_data, "different_bot_token_xxxxx")


# ─────────────────────────────────────────────────────────
# _extract_tg_id
# ─────────────────────────────────────────────────────────


class TestExtractTgId:
    """_extract_tg_id: парсинг поля user (JSON-строка с данными юзера)."""

    def test_valid_extracts_id(self, patched_bot_token):
        parsed = {"user": '{"id": 987654, "first_name": "Alice"}'}
        assert _extract_tg_id(parsed) == 987654

    def test_no_user_field_raises(self, patched_bot_token):
        with pytest.raises(ValueError, match="user"):
            _extract_tg_id({})

    def test_invalid_json_raises(self, patched_bot_token):
        # Невалидный JSON в user → json.JSONDecodeError оборачивается в ValueError.
        with pytest.raises(ValueError, match="JSON"):
            _extract_tg_id({"user": "not valid json"})

    def test_no_id_in_user_raises(self, patched_bot_token):
        with pytest.raises(ValueError, match="id"):
            _extract_tg_id({"user": '{"first_name": "Bob"}'})

    def test_id_as_string_raises(self, patched_bot_token):
        # id="abc" не пройдёт int() — должна быть ошибка.
        with pytest.raises(ValueError):
            _extract_tg_id({"user": '{"id": "abc"}'})


# ─────────────────────────────────────────────────────────
# validate_login_widget (Telegram Login Widget, используется в админке)
# ─────────────────────────────────────────────────────────


class TestValidateLoginWidget:
    """validate_login_widget: валидация подписи для браузерной админки.

    Алгоритм чуть другой, чем у initData: secret_key = SHA256(bot_token),
    а не HMAC-SHA256(WebAppData, bot_token). Это легко перепутать при
    копипасте — тесты на разные bot_token защищают от регрессии.
    """

    def test_valid_returns_tg_id(self, patched_bot_token):
        data = build_login_widget_data(TEST_BOT_TOKEN, user_id=424242)
        assert validate_login_widget(data, TEST_BOT_TOKEN) == 424242

    def test_no_id_raises(self, patched_bot_token):
        data = build_login_widget_data(TEST_BOT_TOKEN)
        del data["id"]
        with pytest.raises(ValueError, match="id"):
            validate_login_widget(data, TEST_BOT_TOKEN)

    def test_no_auth_date_raises(self, patched_bot_token):
        data = build_login_widget_data(TEST_BOT_TOKEN)
        del data["auth_date"]
        with pytest.raises(ValueError, match="auth_date"):
            validate_login_widget(data, TEST_BOT_TOKEN)

    def test_no_hash_raises(self, patched_bot_token):
        data = build_login_widget_data(TEST_BOT_TOKEN)
        del data["hash"]
        with pytest.raises(ValueError, match="hash"):
            validate_login_widget(data, TEST_BOT_TOKEN)

    def test_expired_auth_date_raises(self, patched_bot_token, monkeypatch):
        # Подкручиваем часы на 10 минут вперёд — replay-защита должна сработать.
        real_auth_date = int(time.time())
        monkeypatch.setattr("time.time", lambda: real_auth_date + 600)
        data = build_login_widget_data(TEST_BOT_TOKEN, auth_date=real_auth_date)
        with pytest.raises(ValueError, match="устарел"):
            validate_login_widget(data, TEST_BOT_TOKEN)

    def test_future_auth_date_raises(self, patched_bot_token, monkeypatch):
        # auth_date на 10 минут в будущем — clock skew защита.
        now = int(time.time())
        future_auth_date = now + 600
        monkeypatch.setattr("time.time", lambda: now)
        data = build_login_widget_data(TEST_BOT_TOKEN, auth_date=future_auth_date)
        with pytest.raises(ValueError, match="будущего"):
            validate_login_widget(data, TEST_BOT_TOKEN)

    def test_invalid_hash_raises(self, patched_bot_token):
        data = build_login_widget_data(TEST_BOT_TOKEN)
        data["hash"] = "d" * 64  # 64 hex, но неправильный
        with pytest.raises(ValueError, match="hash"):
            validate_login_widget(data, TEST_BOT_TOKEN)

    def test_wrong_bot_token_raises(self, patched_bot_token):
        data = build_login_widget_data(TEST_BOT_TOKEN)
        with pytest.raises(ValueError, match="hash"):
            validate_login_widget(data, "different_token_xxxxx")

    def test_does_not_mutate_input(self, patched_bot_token):
        # Внутри функции есть data = dict(data) — защита от неожиданных
        # side effects на caller'е (раньше pop() мутировал входной dict).
        # Этот тест ловит регрессию, если кто-то уберёт защитную копию.
        data = build_login_widget_data(TEST_BOT_TOKEN)
        snapshot = dict(data)
        validate_login_widget(data, TEST_BOT_TOKEN)
        assert data == snapshot, "validate_login_widget must not mutate input dict"
