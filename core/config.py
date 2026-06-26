"""Конфигурация приложения через переменные окружения."""

from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Основные настройки приложения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Telegram Bot
    bot_token: SecretStr
    bot_admin_ids: list[int] = []

    # Database
    database_url: str

    # Telegram WebApp URL
    webapp_url: str = "https://onyxvpn.app"

    # Amnezia VPN: работаем через docker exec в контейнер amnezia-awg2,
    # а не через отдельный HTTP API. Эти два параметра задают endpoint Amnezia.
    # Значение по умолчанию — актуальный production IP сервера. Если меняется
    # хост — обязательно обновить и тут, иначе vpn:// URL будет указывать на
    # старый IP (см. audit #1).
    amnezia_server_host: str = "72.56.96.52"  # Публичный IP сервера
    amnezia_container_name: str = "amnezia-awg2"  # Имя контейнера AmneziaWG

    # Payment (ЮKassa СБП)
    yukassa_shop_id: str | None = None
    yukassa_secret_key: SecretStr | None = None

    # Trial period (дни). Используется в api/routes.py:activate_trial
    # и bot/services/scheduler.py для расчёта expires_at и уведомлений.
    trial_days: int = 3

    # Пороги уведомлений (часов до окончания подписки).
    # Используются в bot/services/scheduler.py для пушей "за 24ч" и "за 1ч".
    notification_24h_before: int = 24
    notification_1h_before: int = 1

    # Admin session: TTL сессии админ-панели в секундах (по умолчанию 24 часа).
    # Сессия хранится в AdminSession и автоматически отклоняется после истечения.
    admin_session_ttl_seconds: int = 24 * 60 * 60

    # Интервал фонового сбора трафика WireGuard из Amnezia-контейнера (секунды).
    # Запускается при старте api/main.py и затем повторяется каждые N секунд.
    # Минимум 30 сек (защита от случайного "0" → busy loop).
    # В проде 5 минут — баланс между свежестью данных и нагрузкой на Docker.
    traffic_collect_interval_seconds: int = 300
    # Отключить фоновый сборщик (например, в тестах или если контейнер Amnezia
    # ещё не развёрнут в dev-окружении). В проде оставлять True.
    traffic_collector_enabled: bool = True

    # Payment stub: если True — /payment/create сразу зачисляет деньги на баланс
    # без обращения к ЮKassa. Используется пока не подключён реальный провайдер.
    # В проде ОБЯЗАТЕЛЬНО False (см. audit #2): иначе любой POST /api/payment/create
    # зачислит деньги без реальной оплаты. Если в проде остался True — это критический
    # финансовый баг, проверяйте .env: должно быть PAYMENT_STUB_MODE=False.
    payment_stub_mode: bool = True

    # Шифрование connection_url в БД (Fernet, симметричный AES-128 + HMAC).
    # Если ключ не задан — encryption отключён, connection_url хранится plaintext
    # (для обратной совместимости при разработке). В проде ОБЯЗАТЕЛЬНО задать.
    # Генерация ключа:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    db_encryption_key: SecretStr | None = None

    # Observability (см. core/logging.py и core/metrics.py)
    # ─────────────────────────────────────────────────────────
    # Уровень логирования. Применяется к ВСЕМ логгерам через logging.basicConfig.
    log_level: str = "INFO"

    # Формат логов: "console" (цветной, человекочитаемый — для dev) или
    # "json" (одна строка JSON на лог — для log aggregator'ов в проде).
    log_format: Literal["console", "json"] = "console"

    # Порт для /metrics endpoint бота (uvicorn FastAPI экспозит свои метрики
    # через api/main.py на 8000, бот — отдельный процесс на своём порту).
    # Не маппим наружу в docker-compose — Prometheus ходит через Docker network.
    metrics_bot_port: int = 9100

    # Директория для shared memory prometheus_client в multiprocess-режиме
    # (uvicorn --workers 4 создаёт 4 отдельных процесса, каждый пишет свои
    # метрики в .db-файлы здесь, /metrics handler агрегирует через
    # MultiProcessCollector).
    prometheus_multiproc_dir: str = "/tmp/prometheus_multiproc"

    # Рассылки (broadcasts) в админке.
    # ─────────────────────────────────────────────────────────
    # Лимит Telegram API на отправку сообщений в одном чате/группе —
    # около 30 msg/sec на бот-токен (жёсткий лимит). Ставим 25 с запасом,
    # чтобы при батче в 100 юзеров не упереться в flood-wait.
    broadcast_rate_limit_per_sec: int = 25
    # Размер одного батча для обновления счётчиков кампании в БД.
    # Слишком маленький → много commit-ов, медленно.
    # Слишком большой → потеряем точность счётчиков при крэше.
    # 100 — баланс: ~4 коммита на кампанию в 400 юзеров.
    broadcast_batch_size: int = 100

    @field_validator("bot_admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v) -> list[int]:
        """Парсит строку/число в список ID администраторов."""
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            v = v.strip().strip("[]")
            if not v:
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return []

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Проверка формата URL базы данных.

        Поддерживаемые схемы:
        - postgresql+asyncpg://...  (прод)
        - sqlite+aiosqlite:///...    (локальная разработка / E2E тесты)
        """
        if v.startswith("postgresql+asyncpg://"):
            return v
        if v.startswith("sqlite+aiosqlite://"):
            return v
        raise ValueError(
            "database_url должен начинаться с 'postgresql+asyncpg://' или "
            "'sqlite+aiosqlite://'"
        )


settings = Settings()
