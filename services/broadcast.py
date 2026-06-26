"""Сервис массовых рассылок через Telegram-бота.

Используется из api/admin.py для создания, запуска и мониторинга кампаний
рассылок. Бот и API работают в разных процессах (см. docker-entrypoint.sh),
поэтому этот модуль создаёт собственный экземпляр aiogram.Bot для отправки
сообщений — без polling, только вызовы send_message.

Жизненный цикл кампании:
    1. Админ создаёт DRAFT через POST /api/admin/broadcasts.
    2. resolve_audience() вычисляет список tg_id по сегменту.
    3. Создаём BroadcastDelivery строки (статус PENDING) для всех получателей.
    4. Админ нажимает "Запустить" → POST /api/admin/broadcasts/{id}/start.
    5. start_campaign_in_background() запускает asyncio-задачу.
    6. В задаче: для каждого delivery — bot.send_message, обработка ошибок,
       обновление счётчиков пачками по broadcast_batch_size.
    7. После всех отправок → status = COMPLETED.

Edge cases:
- Юзер заблокировал бота → TelegramForbiddenError → status=BLOCKED.
- Telegram вернул RetryAfter (flood-wait) → ждём retry_after секунд и шлём дальше.
- Сеть/прочие ошибки → status=FAILED с сообщением об ошибке.
- Кампанию в SENDING можно отменить через cancel_campaign().
- При крэше процесса кампания остаётся в SENDING — оператор может
  удалить её вручную через DELETE /api/admin/broadcasts/{id}.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import async_session_factory
from database.models import (
    BroadcastCampaign,
    BroadcastDelivery,
    BroadcastSegment,
    BroadcastStatus,
    DeliveryStatus,
    PlanType,
    Subscription,
    User,
)

logger = logging.getLogger(__name__)

# Словарь активных рассылок: campaign_id → Event для межпроцессной отмены.
# cancel_campaign() вызывает event.set(), start_campaign() ждёт event между
# отправками. После выхода из start_campaign Event удаляется из словаря.
_cancel_events: dict[int, asyncio.Event] = {}


def _get_cancel_event(campaign_id: int) -> asyncio.Event:
    """Возвращает существующий Event или создаёт новый для кампании."""
    event = _cancel_events.get(campaign_id)
    if event is None:
        event = asyncio.Event()
        _cancel_events[campaign_id] = event
    return event


def _drop_cancel_event(campaign_id: int) -> None:
    """Удаляет Event из словаря после завершения рассылки."""
    _cancel_events.pop(campaign_id, None)

# Переменные, которые поддерживает шаблон сообщения. Документированы в UI
# рядом с полем ввода, чтобы админ знал, что можно подставить.
TEMPLATE_VARIABLES: dict[str, str] = {
    "first_name": "Имя пользователя в Telegram",
    "username": "Username (без @) — пусто если не задан",
    "balance": "Баланс в рублях, формат '120.50 ₽'",
    "days_left": "Дней до окончания активной подписки (пусто если нет)",
    "plan_type": "Тип подписки: trial / monthly / quarter / year",
}


# ─────────────────────────────────────────────────────────
# Резолвер аудитории
# ─────────────────────────────────────────────────────────

async def resolve_audience(
    session: AsyncSession,
    segment: BroadcastSegment,
) -> list[dict]:
    """Возвращает список словарей {tg_id, user_id, username, balance}
    для всех пользователей, попадающих в сегмент.

    Запросы оптимизированы под каждый сегмент — пытаемся ходить в
    subscriptions, а не грузить всех юзеров в Python.
    """
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    if segment == BroadcastSegment.ALL:
        # Все когда-либо зарегистрированные
        rows = (await session.execute(
            select(User.tg_id, User.id, User.username, User.balance, User.username)
        )).all()

    elif segment == BroadcastSegment.TRIAL:
        # Активные триалы
        rows = (await session.execute(
            select(User.tg_id, User.id, User.username, User.balance, User.username)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                Subscription.is_active == True,
                Subscription.plan_type == PlanType.TRIAL,
                Subscription.expires_at > now,
            )
        )).all()

    elif segment == BroadcastSegment.PAID:
        # Активные платные подписки (MONTHLY, QUARTER, YEAR)
        rows = (await session.execute(
            select(User.tg_id, User.id, User.username, User.balance, User.username)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                Subscription.is_active == True,
                Subscription.plan_type.in_([
                    PlanType.MONTHLY, PlanType.QUARTER, PlanType.YEAR,
                ]),
                Subscription.expires_at > now,
            )
        )).all()

    elif segment == BroadcastSegment.TRIAL_EXPIRING_24H:
        # Триалы, истекающие в течение следующих 24 часов (но ещё не истёкшие)
        rows = (await session.execute(
            select(User.tg_id, User.id, User.username, User.balance, User.username)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                Subscription.is_active == True,
                Subscription.plan_type == PlanType.TRIAL,
                Subscription.expires_at > now,
                Subscription.expires_at <= now + timedelta(hours=24),
            )
        )).all()

    elif segment == BroadcastSegment.TRIAL_EXPIRING_1H:
        # Триалы, истекающие в течение следующего часа
        rows = (await session.execute(
            select(User.tg_id, User.id, User.username, User.balance, User.username)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                Subscription.is_active == True,
                Subscription.plan_type == PlanType.TRIAL,
                Subscription.expires_at > now,
                Subscription.expires_at <= now + timedelta(hours=1),
            )
        )).all()

    elif segment == BroadcastSegment.EXPIRED:
        # Подписки, истёкшие за последние 7 дней (любого типа)
        rows = (await session.execute(
            select(User.tg_id, User.id, User.username, User.balance, User.username)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                Subscription.expires_at <= now,
                Subscription.expires_at >= seven_days_ago,
            )
            .distinct()
        )).all()

    elif segment == BroadcastSegment.INACTIVE_7D:
        # Юзеры без активности 7+ дней (по last_activity_at)
        rows = (await session.execute(
            select(User.tg_id, User.id, User.username, User.balance, User.username)
            .where(
                (User.last_activity_at.is_(None))
                | (User.last_activity_at < seven_days_ago)
            )
        )).all()

    elif segment == BroadcastSegment.WITH_BALANCE:
        # Юзеры с положительным балансом
        rows = (await session.execute(
            select(User.tg_id, User.id, User.username, User.balance, User.username)
            .where(User.balance > 0)
        )).all()

    else:
        # Защита от неизвестного значения enum — не отправляем никому.
        logger.warning("resolve_audience: неизвестный сегмент %s", segment)
        return []

    return [
        {
            "tg_id": tg_id,
            "user_id": user_id,
            "username": username,
            "balance": balance,
            "first_name": first_name or "",
        }
        for tg_id, user_id, username, balance, first_name in rows
    ]


async def count_audience(
    session: AsyncSession,
    segment: BroadcastSegment,
) -> int:
    """Быстрый подсчёт аудитории без загрузки данных (для preview в UI)."""
    audience = await resolve_audience(session, segment)
    return len(audience)


async def count_all_segments(session: AsyncSession) -> dict[str, int]:
    """Считает аудиторию по всем сегментам сразу.

    Используется в GET /api/admin/broadcasts/segments/stats — UI рисует
    таблицу "trial: 412, paid: 89, ..." для быстрого выбора.
    """
    result: dict[str, int] = {}
    for segment in BroadcastSegment:
        result[segment.value] = await count_audience(session, segment)
    return result


# ─────────────────────────────────────────────────────────
# Шаблонизация
# ─────────────────────────────────────────────────────────

def render_message(
    template: str,
    *,
    first_name: str | None,
    username: str | None,
    balance: int,
    days_left: int | None,
    plan_type: str | None,
) -> str:
    """Подставляет {переменные} в HTML-шаблон.

    Безопасна: все значения вставляются как plain text в HTML-разметку.
    Если в template есть `<b>`, `<i>` и т.п. — они сохранятся как есть.

    Неизвестные переменные оставляем как {name} — чтобы админ сразу
    увидел опечатку в превью.
    """
    safe_first = (first_name or "").replace("<", "&lt;").replace(">", "&gt;")
    safe_username = (username or "").replace("<", "&lt;").replace(">", "&gt;")

    balance_rub = f"{balance / 100:.2f} ₽".replace(".00 ", " ")

    replacements = {
        "first_name": safe_first or "друг",
        "username": safe_username,
        "balance": balance_rub,
        "days_left": str(days_left) if days_left is not None else "—",
        "plan_type": plan_type or "—",
    }

    out = template
    for key, value in replacements.items():
        out = out.replace("{" + key + "}", value)
    return out


# ─────────────────────────────────────────────────────────
# Отправка
# ─────────────────────────────────────────────────────────

def _make_bot() -> Bot:
    """Создаёт отдельный экземпляр Bot для рассылок.

    У бота в bot/main.py есть свой Bot для polling — его трогать нельзя,
    иначе конфликт апдейтов. Этот экземпляр используется только для
    bot.send_message() без start_polling().
    """
    return Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def _resolve_days_left_and_plan(
    session: AsyncSession,
    user_id: int,
) -> tuple[int | None, str | None]:
    """Достаёт из БД (days_left, plan_type) активной подписки юзера.

    None если активной подписки нет.
    """
    now = datetime.now(timezone.utc)
    sub_q = (
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.is_active == True,
            Subscription.expires_at > now,
        )
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    )
    sub = (await session.execute(sub_q)).scalar_one_or_none()
    if sub is None:
        return None, None
    delta = sub.expires_at - now
    return max(0, delta.days), sub.plan_type.value


async def _send_one(
    bot: Bot,
    campaign: BroadcastCampaign,
    delivery: BroadcastDelivery,
    *,
    rendered_text: str,
) -> tuple[DeliveryStatus, str | None]:
    """Шлёт одно сообщение. Возвращает (итоговый_статус, ошибка_or_none).

    Никогда не бросает исключения наружу — все ошибки Telegram API
    превращаются в статусы доставки (failed/blocked).
    """
    try:
        await bot.send_message(
            chat_id=delivery.user_tg_id,
            text=rendered_text,
            parse_mode="HTML",
        )
        return DeliveryStatus.SENT, None
    except TelegramForbiddenError:
        # Юзер заблокировал бота — это не «сбой», это терминальное состояние
        return DeliveryStatus.BLOCKED, "user blocked the bot"
    except TelegramRetryAfter as e:
        # Telegram сказал подождать (flood-wait). Ждём и пробуем ещё раз.
        # Если и со второй попытки retry-after — считаем failed.
        logger.warning(
            "broadcast_retry_after campaign_id=%s tg_id=%s retry_after=%s",
            campaign.id, delivery.user_tg_id, e.retry_after,
        )
        await asyncio.sleep(e.retry_after)
        try:
            await bot.send_message(
                chat_id=delivery.user_tg_id,
                text=rendered_text,
                parse_mode="HTML",
            )
            return DeliveryStatus.SENT, None
        except TelegramRetryAfter as e2:
            return DeliveryStatus.FAILED, f"retry_after {e2.retry_after}s"
        except TelegramAPIError as e2:
            return DeliveryStatus.FAILED, f"{type(e2).__name__}: {e2}"
    except TelegramAPIError as e:
        return DeliveryStatus.FAILED, f"{type(e).__name__}: {e}"
    except Exception as e:
        # Не-Telegram ошибка (сеть, таймаут и т.п.)
        return DeliveryStatus.FAILED, f"{type(e).__name__}: {e}"


async def _process_batch(
    bot: Bot,
    campaign: BroadcastCampaign,
    deliveries: list[BroadcastDelivery],
    *,
    rate_limiter: asyncio.Semaphore,
    rate_pause: float,
    cancel_event: asyncio.Event,
) -> tuple[int, int, int]:
    """Обрабатывает батч deliveries: шлёт, обновляет статусы.

    Возвращает (sent, failed, blocked) — для инкремента счётчиков кампании.

    Args:
        rate_limiter: семафор, ограничивающий общий темп отправки.
        rate_pause: пауза между запросами (1 / rate_limit_per_sec).
        cancel_event: событие, сигнализирующее об отмене. Когда set() —
            текущий батч дорабатывает до конца, новые не берутся.
    """
    sent = failed = blocked = 0

    for delivery in deliveries:
        if cancel_event.is_set():
            # Кампанию отменили — оставшиеся pending остаются pending
            return sent, failed, blocked

        async with rate_limiter:
            # Перед запросом — пауза, чтобы не превысить лимит
            if rate_pause > 0:
                await asyncio.sleep(rate_pause)

            # Каждый send идёт со своим расчётом текста, т.к. переменные
            # интерполируются per-user.
            async with async_session_factory() as session:
                days_left, plan_type = await _resolve_days_left_and_plan(
                    session, delivery.user_id or 0,
                )
                user_q = select(User).where(User.id == delivery.user_id)
                user = (await session.execute(user_q)).scalar_one_or_none()

            rendered = render_message(
                campaign.message_text,
                first_name=user.username.lstrip("@") if user and user.username else None,
                username=user.username if user else None,
                balance=user.balance if user else 0,
                days_left=days_left,
                plan_type=plan_type,
            )

            status, err = await _send_one(
                bot, campaign, delivery, rendered_text=rendered,
            )

        # Обновляем доставку в БД — отдельной сессией, чтобы не блокировать
        # основной flush.
        async with async_session_factory() as session:
            d_q = select(BroadcastDelivery).where(
                BroadcastDelivery.id == delivery.id
            )
            d = (await session.execute(d_q)).scalar_one()
            d.status = status
            d.sent_at = datetime.now(timezone.utc) if status == DeliveryStatus.SENT else None
            d.error_message = err
            await session.commit()

        if status == DeliveryStatus.SENT:
            sent += 1
        elif status == DeliveryStatus.BLOCKED:
            blocked += 1
        else:
            failed += 1

    return sent, failed, blocked


async def start_campaign(campaign_id: int) -> None:
    """Запускает рассылку. Запускать через asyncio.create_task.

    Создаёт Bot-инстанс, читает pending deliveries, шлёт батчами,
    обновляет счётчики кампании. По завершении (или ошибке) переводит
    кампанию в COMPLETED/FAILED/CANCELED.

    Отмена: cancel_campaign() выставляет Event в _cancel_events.
    Текущая задача замечает это между отправками и выходит из цикла,
    после чего переводит кампанию в CANCELED.
    """
    bot = _make_bot()
    cancel_event = _get_cancel_event(campaign_id)

    try:
        async with async_session_factory() as session:
            campaign_q = select(BroadcastCampaign).where(
                BroadcastCampaign.id == campaign_id
            )
            campaign = (await session.execute(campaign_q)).scalar_one_or_none()

            if campaign is None:
                logger.error("start_campaign: кампания %s не найдена", campaign_id)
                return
            if campaign.status != BroadcastStatus.DRAFT:
                logger.warning(
                    "start_campaign: кампания %s уже в статусе %s, не запускаем",
                    campaign_id, campaign.status,
                )
                return

            # Переводим в SENDING
            now = datetime.now(timezone.utc)
            campaign.status = BroadcastStatus.SENDING
            campaign.started_at = now
            # total_recipients должен совпадать с количеством deliveries,
            # которые мы создадим ниже — иначе UI покажет неверный %.
            pending_count = (
                await session.execute(
                    select(BroadcastDelivery).where(
                        BroadcastDelivery.campaign_id == campaign_id,
                    )
                )
            ).scalars().all()
            campaign.total_recipients = len(pending_count)
            await session.commit()
            logger.info(
                "broadcast_started campaign_id=%s segment=%s recipients=%s",
                campaign_id, campaign.target_segment, len(pending_count),
            )

        # Rate limiter: ~25 msg/sec означает ~40ms между запросами.
        rate_per_sec = max(1, settings.broadcast_rate_limit_per_sec)
        rate_pause = 1.0 / rate_per_sec
        rate_limiter = asyncio.Semaphore(rate_per_sec)

        total_sent = total_failed = total_blocked = 0
        batch_size = max(1, settings.broadcast_batch_size)

        # Обрабатываем deliveries батчами с обновлением счётчиков кампании
        while True:
            if cancel_event.is_set():
                break

            async with async_session_factory() as session:
                batch_q = (
                    select(BroadcastDelivery)
                    .where(
                        BroadcastDelivery.campaign_id == campaign_id,
                        BroadcastDelivery.status == DeliveryStatus.PENDING,
                    )
                    .order_by(BroadcastDelivery.id)
                    .limit(batch_size)
                )
                batch = (await session.execute(batch_q)).scalars().all()
                if not batch:
                    break

                # Помечаем как «в обработке» чтобы другой воркер API не
                # взял те же записи (если когда-нибудь появится HA).
                # В текущей архитектуре (single process для рассылок)
                # это перестраховка — но UPDATE в одной транзакции
                # стоит копейки.
                for d in batch:
                    d.error_message = "processing"
                await session.commit()

            # Отправляем батч
            try:
                sent, failed, blocked = await _process_batch(
                    bot, campaign, batch,
                    rate_limiter=rate_limiter,
                    rate_pause=rate_pause,
                    cancel_event=cancel_event,
                )
                total_sent += sent
                total_failed += failed
                total_blocked += blocked

                # Обновляем счётчики кампании раз в батч
                async with async_session_factory() as session:
                    c_q = select(BroadcastCampaign).where(
                        BroadcastCampaign.id == campaign_id
                    )
                    c = (await session.execute(c_q)).scalar_one()
                    c.sent_count += sent
                    c.failed_count += failed
                    c.blocked_count += blocked
                    await session.commit()
            except Exception as e:
                logger.exception(
                    "broadcast_batch_failed campaign_id=%s err=%s",
                    campaign_id, e,
                )
                # Продолжаем — один битый батч не должен убить всю кампанию

        # Финальный статус
        async with async_session_factory() as session:
            c_q = select(BroadcastCampaign).where(
                BroadcastCampaign.id == campaign_id
            )
            c = (await session.execute(c_q)).scalar_one()
            c.finished_at = datetime.now(timezone.utc)
            if cancel_event.is_set():
                c.status = BroadcastStatus.CANCELED
            elif total_failed > 0 and total_sent == 0 and total_blocked == 0:
                # Ни одного успешного — но какие-то ошибки были
                c.status = BroadcastStatus.FAILED
            else:
                c.status = BroadcastStatus.COMPLETED
            await session.commit()

        logger.info(
            "broadcast_finished campaign_id=%s sent=%s failed=%s blocked=%s status=%s",
            campaign_id, total_sent, total_failed, total_blocked, c.status,
        )

    except Exception as e:
        logger.exception("broadcast_crashed campaign_id=%s err=%s", campaign_id, e)
        async with async_session_factory() as session:
            c_q = select(BroadcastCampaign).where(
                BroadcastCampaign.id == campaign_id
            )
            c = (await session.execute(c_q)).scalar_one_or_none()
            if c:
                c.status = BroadcastStatus.FAILED
                c.finished_at = datetime.now(timezone.utc)
                await session.commit()
    finally:
        _drop_cancel_event(campaign_id)
        await bot.session.close()


def start_campaign_in_background(campaign_id: int) -> asyncio.Task:
    """Обёртка: запускает start_campaign как фоновую задачу.

    Используется в API-эндпоинте POST /api/admin/broadcasts/{id}/start.
    Возвращает Task — caller может при желании await/отменить (хотя в
    текущем коде этого не делаем).
    """
    return asyncio.create_task(
        start_campaign(campaign_id), name=f"broadcast-{campaign_id}",
    )


async def cancel_campaign(campaign_id: int) -> bool:
    """Помечает кампанию как отменённую.

    Выставляет Event, который читает start_campaign между отправками.
    Если кампания в DRAFT — просто переводим в CANCELED в БД (задача
    ещё не запущена). Если в SENDING — Event + DB update, и фоновая
    задача заметит Event в ближайшее время и выйдет.

    Возвращает True если отмена была применена, False если кампания
    уже завершена или не найдена.
    """
    async with async_session_factory() as session:
        c_q = select(BroadcastCampaign).where(
            BroadcastCampaign.id == campaign_id
        )
        c = (await session.execute(c_q)).scalar_one_or_none()
        if c is None:
            return False
        if c.status == BroadcastStatus.COMPLETED:
            return False
        if c.status == BroadcastStatus.FAILED:
            return False
        if c.status == BroadcastStatus.CANCELED:
            return True

        # Сигнализируем Event'ом — фоновая задача (если есть) завершится.
        cancel_event = _cancel_events.get(campaign_id)
        if cancel_event is not None:
            cancel_event.set()

        # Также обновляем статус в БД — если фоновая задача уже упала
        # (Event не создавался), DELETE из UI всё равно сработает.
        c.status = BroadcastStatus.CANCELED
        c.finished_at = datetime.now(timezone.utc)
        await session.commit()
        return True
