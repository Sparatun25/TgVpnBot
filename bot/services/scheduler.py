"""Планировщик уведомлений о триале и истёкших подписках."""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.utils.markdown import hbold, hitalic
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.db import async_session_factory
from database.models import Subscription, User
from services.amnezia import check_expired_subscriptions

logger = logging.getLogger(__name__)


async def send_trial_24h_notification(bot: Bot) -> None:
    """
    Отправить уведомление за 24 часа до окончания триала.

    Ищет пользователей с активным триалом, у которых осталось от 23 до 24 часов,
    и которые ещё не получали это уведомление.
    """
    now = datetime.now(timezone.utc)
    time_24h = now + timedelta(hours=24)
    time_23h = now + timedelta(hours=23)

    async with async_session_factory() as session:
        # Ищем активные триалы, которые истекают в диапазоне 23-24 часа
        query = (
            select(User)
            .join(Subscription)
            .where(
                Subscription.is_active == True,
                Subscription.plan_type == "trial",
                Subscription.expires_at >= time_23h,
                Subscription.expires_at <= time_24h,
                User.notified_24h == False,
            )
            .options(selectinload(User.subscriptions))
        )

        result = await session.execute(query)
        users = result.scalars().all()

        if not users:
            logger.debug("Нет пользователей для уведомления за 24 часа")
            return

        logger.info("Найдено %s пользователей для уведомления за 24 часа", len(users))

        for user in users:
            try:
                # Формируем красивое сообщение
                message_text = (
                    f"{hbold('✨ Ваша подписка скоро завершится')}\n\n"
                    f"До окончания бесплатного периода осталось менее 24 часов.\n\n"
                    f"{hitalic('Не хотите потерять доступ?')}\n"
                    f"Пополните баланс в приложении и выберите подходящий тариф.\n\n"
                    f"🔐 OnyxVpn — свобода без ограничений"
                )

                await bot.send_message(
                    chat_id=user.tg_id,
                    text=message_text,
                    parse_mode="HTML",
                )

                # Отмечаем, что уведомление отправлено
                user.notified_24h = True
                await session.commit()

                logger.info("Отправлено уведомление за 24 часа: user_id=%s", user.tg_id)

            except Exception as e:
                logger.error(
                    "Ошибка отправки уведомления пользователю %s: %s",
                    user.tg_id,
                    e,
                )
                # Продолжаем обрабатывать остальных пользователе��
                continue


async def send_trial_1h_notification(bot: Bot) -> None:
    """
    Отправить уведомление за 1 час до окончания триала.

    Ищет пользователей с активным триалом, у которых осталось ровно 1 час,
    и которые ещё не получали это уведомление.
    """
    now = datetime.now(timezone.utc)
    time_1h = now + timedelta(hours=1)
    time_59m = now + timedelta(minutes=59)

    async with async_session_factory() as session:
        # Ищем активные триалы, которые истекают в диапазоне 59-60 минут
        query = (
            select(User)
            .join(Subscription)
            .where(
                Subscription.is_active == True,
                Subscription.plan_type == "trial",
                Subscription.expires_at >= time_59m,
                Subscription.expires_at <= time_1h,
                User.notified_1h == False,
            )
            .options(selectinload(User.subscriptions))
        )

        result = await session.execute(query)
        users = result.scalars().all()

        if not users:
            logger.debug("Нет пользователей для уведомления за 1 час")
            return

        logger.info("Найдено %s пользователей для уведомления за 1 час", len(users))

        for user in users:
            try:
                # Формируем финальное предупреждение
                message_text = (
                    f"{hbold('⚠️ Последний час подписки!')}\n\n"
                    f"Ваш бесплатный период завершится через 1 час.\n\n"
                    f"{hitalic('Пополните баланс прямо сейчас, чтобы сохранить доступ:')}\n"
                    f"📱 Откройте приложение → Баланс → Пополнить через СБП\n\n"
                    f"После пополнения выберите тариф и продлите подписку.\n\n"
                    f"✨ OnyxVpn — ваш надёжный VPN"
                )

                await bot.send_message(
                    chat_id=user.tg_id,
                    text=message_text,
                    parse_mode="HTML",
                )

                # Отмечаем, что уведомление отправлено
                user.notified_1h = True
                await session.commit()

                logger.info("Отправлено уведомление за 1 час: user_id=%s", user.tg_id)

            except Exception as e:
                logger.error(
                    "Ошибка отправки уведомления пользователю %s: %s",
                    user.tg_id,
                    e,
                )
                continue


async def cleanup_expired_subscriptions(bot: Bot) -> None:
    """
    Очистить истёкшие подписки и отозвать ключи Amnezia.

    Вызывает метод check_expired_subscriptions из services/amnezia.py.
    """
    async with async_session_factory() as session:
        try:
            revoked = await check_expired_subscriptions(session)

            if revoked:
                logger.info("Отозвано %s истёкших ключей", len(revoked))

                # Отправляем уведомления пользователям об окончании подписки
                for sub in revoked:
                    try:
                        message_text = (
                            f"{hbold('🔒 Подписка завершена')}\n\n"
                            f"Ваш бесплатный период или подписка истекли.\n\n"
                            f"{hitalic('Хотите продолжить?')}\n"
                            f"Откройте приложение и выберите подходящий тариф.\n\n"
                            f"✨ OnyxVpn — свобода без ограничений"
                        )

                        await bot.send_message(
                            chat_id=sub.user.tg_id,
                            text=message_text,
                            parse_mode="HTML",
                        )

                        logger.info(
                            "Отправлено уведомление об окончании: user_id=%s",
                            sub.user.tg_id,
                        )

                    except Exception as e:
                        logger.error(
                            "Ошибка отправки уведомления об окончании пользователю %s: %s",
                            sub.user.tg_id,
                            e,
                        )

        except Exception as e:
            logger.error("Ошибка очистки истёкших подписок: %s", e)


async def start_notification_scheduler(bot: Bot) -> AsyncIOScheduler:
    """
    Запустить планировщик уведомлений.

    Создаёт и запускает APScheduler с тремя задачами:
    1. Проверка уведомлений за 24 часа (каждую минуту)
    2. Проверка уведомлений за 1 час (каждую минуту)
    3. Очистка истёкших подписок (каждую минуту)

    Returns:
        Запущенный планировщик.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Задача 1: Уведомления за 24 часа
    scheduler.add_job(
        send_trial_24h_notification,
        trigger="interval",
        minutes=1,
        args=[bot],
        id="trial_24h_notification",
        name="Trial 24h notification",
        replace_existing=True,
    )

    # Задача 2: Уведомления за 1 час
    scheduler.add_job(
        send_trial_1h_notification,
        trigger="interval",
        minutes=1,
        args=[bot],
        id="trial_1h_notification",
        name="Trial 1h notification",
        replace_existing=True,
    )

    # Задача 3: Очистка истёкших подписок
    scheduler.add_job(
        cleanup_expired_subscriptions,
        trigger="interval",
        minutes=1,
        args=[bot],
        id="cleanup_expired",
        name="Cleanup expired subscriptions",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Планировщик уведомлений запущен")

    return scheduler
