"""Конфигурация приложения через переменные окружения."""

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Основные настройки приложения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram Bot
    bot_token: SecretStr
    bot_admin_ids: list[int] = []

    # Database
    database_url: str

    # Telegram WebApp URL
    webapp_url: str = "https://onyxvpn.app"

    # Amnezia VPN API
    amnezia_api_url: str = "http://localhost:8080"
    amnezia_api_key: SecretStr | None = None
    amnezia_docker_host: str = "localhost"
    amnezia_server_host: str = "104.171.128.135"  # Публичный IP сервера
    amnezia_container_name: str = "amnezia-awg2"  # Имя контейнера AmneziaWG

    # Payment (ЮKassa СБП)
    yukassa_shop_id: str | None = None
    yukassa_secret_key: SecretStr | None = None

    # Trial period (дни)
    trial_days: int = 3

    # Notification thresholds (часы до окончания)
    notification_24h_before: int = 24
    notification_1h_before: int = 1

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
        """Проверка формата URL базы данных."""
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "database_url должен начинаться с 'postgresql+asyncpg://'"
            )
        return v


settings = Settings()
