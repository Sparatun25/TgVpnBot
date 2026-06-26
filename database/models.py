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


class BroadcastSegment(str, enum.Enum):
    """Сегмент аудитории для рассылки.

    Определяет, кому уйдёт сообщение. Используется в BroadcastCampaign.target_segment
    и резолвится в SQL-запрос в services/broadcast.py:resolve_audience.

    Значения хранятся как строки в PostgreSQL (native_enum=False), чтобы
    добавление нового сегмента не требовало миграции enum-типа.
    """

    TRIAL = "trial"
    """Активные триальные подписки."""

    PAID = "paid"
    """Активные платные подписки (MONTHLY/QUARTER/YEAR)."""

    TRIAL_EXPIRING_24H = "trial_expiring_24h"
    """Триалы, истекающие в ближайшие 24 часа (но ещё не истёкшие)."""

    TRIAL_EXPIRING_1H = "trial_expiring_1h"
    """Триалы, истекающие в ближайший час (но ещё не истёкшие)."""

    EXPIRED = "expired"
    """Подписки, истёкшие за последние 7 дней."""

    INACTIVE_7D = "inactive_7d"
    """Пользователи без активности (last_activity_at < now - 7d)."""

    WITH_BALANCE = "with_balance"
    """Пользователи с положительным балансом (кто-то может купить подписку)."""

    ALL = "all"
    """Все зарегистрированные пользователи."""


class BroadcastStatus(str, enum.Enum):
    """Жизненный цикл рассылки.

    DRAFT → SENDING → COMPLETED
                     → FAILED (если упали с невозможностью продолжить)
                     → CANCELED (админ отменил во время отправки)
    """

    DRAFT = "draft"
    """Создана, ещё не запущена. Можно редактировать и удалять."""

    SENDING = "sending"
    """Идёт отправка. Поля счётчиков обновляются по ходу."""

    COMPLETED = "completed"
    """Успешно завершена: все pending → sent/failed/blocked."""

    CANCELED = "canceled"
    """Отменена админом. Оставшиеся pending остаются pending (для истории)."""

    FAILED = "failed"
    """Критическая ошибка (например, бот сломался). Запустить заново нельзя."""


class DeliveryStatus(str, enum.Enum):
    """Статус доставки одного получателя."""

    PENDING = "pending"
    """Ещё не отправлено (только для canceled кампаний)."""

    SENT = "sent"
    """Успешно отправлено."""

    FAILED = "failed"
    """Ошибка отправки (сетевая, таймаут и т.п.)."""

    BLOCKED = "blocked"
    """Пользователь заблокировал бота (TelegramForbiddenError)."""


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

    # Трафик через WireGuard-туннель. Обновляется фоновым сборщиком
    # services/traffic_collector.py через wg show awg0 в контейнере AmneziaWG.
    # BigInteger: даже при 1 Гбит/с аггрегат за год переваливает за 2^31 байт.
    total_bytes_received: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, server_default=text("0"),
    )
    total_bytes_sent: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, server_default=text("0"),
    )
    # Момент последнего handshake с клиентом (UTC). NULL = ключ создан, но
    # пользователь ещё ни разу не подключился.
    last_handshake_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

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


class BroadcastCampaign(Base):
    """Кампания рассылки.

    Описывает одну массовую отправку сообщения группе пользователей.
    Жизненный цикл: DRAFT → SENDING → COMPLETED|CANCELED|FAILED.
    Счётчики (total_recipients/sent_count/failed_count/blocked_count)
    обновляются в services/broadcast.py по ходу отправки.

    text_message хранится как HTML (с поддержкой {first_name}, {balance},
    {days_left} — интерполяция в render_message).

    Атрибуты:
        title: внутреннее имя кампании для админа (до 100 символов).
        message_text: HTML-текст сообщения.
        target_segment: BroadcastSegment — кому слать.
        status: BroadcastStatus — текущее состояние отправки.
        created_by_tg_id: Telegram ID админа, создавшего кампанию.
        total_recipients: сколько юзеров попали в аудиторию на момент старта.
        sent_count: сколько доставлено успешно.
        failed_count: ошибки (сеть, таймаут и т.п.).
        blocked_count: юзер заблокировал бота.
        started_at: NULL пока кампания в DRAFT.
        finished_at: NULL пока не завершилась (COMPLETED/CANCELED/FAILED).
    """

    __tablename__ = "broadcast_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_segment: Mapped[BroadcastSegment] = mapped_column(
        SAEnum(BroadcastSegment, name="broadcast_segment", native_enum=False, length=30),
        nullable=False,
    )
    status: Mapped[BroadcastStatus] = mapped_column(
        SAEnum(BroadcastStatus, name="broadcast_status", native_enum=False, length=20),
        nullable=False,
        server_default=text("'draft'"),
    )
    created_by_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_recipients: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"),
    )
    sent_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"),
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"),
    )
    blocked_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Relationships
    deliveries: Mapped[list["BroadcastDelivery"]] = relationship(
        "BroadcastDelivery", back_populates="campaign", cascade="all, delete-orphan"
    )


class BroadcastDelivery(Base):
    """Запись о доставке сообщения одному получателю.

    Одна строка = один юзер в аудитории кампании. Создаётся при старте
    кампании (для всех юзеров аудитории сразу), обновляется по ходу
    отправки. После завершения кампании хранится как история.

    user_id — nullable + ON DELETE SET NULL, чтобы удаление юзера из БД
    не каскадировало на историю рассылок (юзер мог отписаться от бота,
    но история кому и когда слали — полезна для админа).

    user_tg_id хранится денормализованным, чтобы можно было показать
    статистику даже после удаления user-записи.
    """

    __tablename__ = "broadcast_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("broadcast_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    status: Mapped[DeliveryStatus] = mapped_column(
        SAEnum(DeliveryStatus, name="delivery_status", native_enum=False, length=20),
        nullable=False,
        server_default=text("'pending'"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Relationships
    campaign: Mapped["BroadcastCampaign"] = relationship(
        "BroadcastCampaign", back_populates="deliveries"
    )
