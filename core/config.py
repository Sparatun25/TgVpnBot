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

    # Telegram WebApp (для валидации initData)
    telegram_bot_token: SecretStr | None = None
    webapp_url: str = "https://onyxvpn.app"

    # Amnezia VPN API
    amnezia_api_url: str = "http://localhost:8080"
    amnezia_api_key: SecretStr | None = None
    amnezia_docker_host: str = "localhost"

    # Payment (ЮKassa СБП)
    yukassa_shop_id: str | None = None
    yukassa_secret_key: SecretStr | None = None

    # Trial period (дни)
    trial_days: int = 3

    # Notification thresholds (часы до окончания)
    notification_24h_before: int = 24
    notification_1h_before: int = 1

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
