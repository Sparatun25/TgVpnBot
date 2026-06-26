"""Модели базы данных."""

import enum
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    BigInteger,
    String,
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для моделей."""

    pass


class PlanType(str, enum.Enum):
    """Тип подписки.

    Значения хранятся в PostgreSQL как ENUM (см. Subscription.plan_type).
    Строковое наследование (str, enum.Enum) позволяет использовать PlanType
    там же, где раньше использовались строки — например, в Pydantic-схемах
    и при сериализации в JSON.
    """

    TRIAL = "trial"
    MONTHLY = "monthly"
    QUARTER = "quarter"
    YEAR = "year"


class PaymentStatus(str, enum.Enum):
    """Статус платежа (по документации ЮKassa).

    Используется в Payment.status. На уровне БД хранится как ENUM,
    что исключает запись произвольных значений вроде "sucessed" (опечатка).
    """

    PENDING = "pending"
    WAITING_FOR_CAPTURE = "waiting_for_capture"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"


class User(Base):
    """Пользователь Telegram."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    # Telegram username — максимум 32 символа (без @). 64 с запасом.
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Реферальная система
    referral_code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    # referred_by_id хранит tg_id пригласившего (не users.id) — именно так используется
    # в admin.py:metrics для подсчёта топ-рефереров. Тип BigInteger, потому что
    # Telegram ID не помещается в Integer (32-bit signed max ≈ 2.1 млрд, а текущий
    # диапазон Telegram уже перевалил за 7 млрд).
    # FK на users.tg_id с SET NULL: если реферер удалён, у рефералов просто
    # обнуляется поле, а запись о реферале сохраняется.
    referred_by_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.tg_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Флаги уведомлений о триале
    notified_24h: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notified_1h: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Отслеживание неактивных ключей
    key_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notified_inactive_15m: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notified_inactive_3h: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notified_inactive_24h: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Баланс не может быть отрицательным. Защита от race condition:
        # если два запроса параллельно спишут деньги, БД отвергнет второй.
        CheckConstraint("balance >= 0", name="ck_users_balance_non_negative"),
    )


class Subscription(Base):
    """Подписка пользователя (ключ Amnezia)."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uuid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    plan_type: Mapped[PlanType] = mapped_column(
        SAEnum(PlanType, name="plan_type", native_enum=False, length=20),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    # vpn:// URL, зашифрованный Fernet (AES-128 + HMAC-SHA256).
    # Если DB_ENCRYPTION_KEY не задан — хранится plaintext (dev-режим).
    # Чтение/запись — через core.crypto.encrypt_connection_url/decrypt_connection_url.
    # Plaintext-значения из старых версий приложения читаются корректно
    # (decrypt_connection_url их просто возвращает как есть).
    connection_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Самый частый запрос: «активная подписка пользователя, которая не истекла».
        # Композитный индекс покрывает WHERE user_id = ? AND is_active = true AND expires_at > now.
        Index(
            "ix_subscriptions_user_active_expires",
            "user_id", "is_active", "expires_at",
        ),
        # Защита от race condition: только одна триальная подписка на пользователя.
        # Partial unique index с where — позволяет иметь сколько угодно
        # платных подписок, но гарантирует уникальность trial.
        # WHERE поддерживается и PostgreSQL, и SQLite (с 3.8.0).
        # В дополнение к прикладной проверке has_used_trial: даже если приложение
        # допустит баг (или придёт параллельный запрос), БД отвергнет второй trial.
        Index(
            "uq_subscriptions_one_trial_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("plan_type = 'trial'"),
            postgresql_where=text("plan_type = 'trial'"),
        ),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="subscriptions")


class Payment(Base):
    """Платеж пользователя."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # в копейках
    payment_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status", native_enum=False, length=30),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Сумма платежа строго положительная. Нулевой или отрицательный
        # платёж — всегда ошибка в логике (защита от багов в /payment/create).
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="payments")


class AdminSession(Base):
    """Сессия администратора после авторизации через Telegram Login Widget.

    Каждой успешной авторизации через Login Widget соответствует одна сессия.
    Сессия идентифицируется случайным токеном (token) и имеет TTL.

    Преимущества перед прежней схемой X-Admin-Tg-Id / числового Bearer:
    - токен не зависит от user_id, его нельзя подобрать перебором;
    - токен можно отозвать (logout / компрометация);
    - по expires_at работает автоматическое истечение.

    Атрибуты:
        tg_id: Telegram ID администратора (без привязки к users.id, потому что
               админ может не иметь записи в users, если он не пользователь VPN).
        token: Случайный URL-safe токен длиной ~43 символа.
        expires_at: TTL задаётся в настройках (по умолчанию 24 часа).
        last_used_at: Обновляется при каждом запросе через require_admin.
    """

    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
