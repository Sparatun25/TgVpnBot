"""Планировщик уведомлений о триале и истёкших подписках."""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.markdown import hbold, hitalic
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.config import settings
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

                # Inline кнопки для быстрого продления
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🚀 Продлить на год за 124₽/мес",
                                web_app={"url": f"{settings.webapp_url}?screen=tariffs&plan=year"},
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="📅 Продлить на месяц",
                                web_app={"url": f"{settings.webapp_url}?screen=tariffs&plan=monthly"},
                            )
                        ],
                    ]
                )

                await bot.send_message(
                    chat_id=user.tg_id,
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
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

                # Inline кнопки для быстрого продления
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🚀 Продлить на год за 124₽/мес",
                                web_app={"url": f"{settings.webapp_url}?screen=tariffs&plan=year"},
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="📅 Продлить на месяц",
                                web_app={"url": f"{settings.webapp_url}?screen=tariffs&plan=monthly"},
                            )
                        ],
                    ]
                )

                await bot.send_message(
                    chat_id=user.tg_id,
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
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


async def send_inactive_key_notifications(bot: Bot) -> None:
    """
    Отправить уведомления пользователям с неактивными ключами.

    Триггеры:
    - 15 минут после создания ключа: "Твой ключ зарезервирован и ждёт подключения"
    - 3 часа после создания ключа: "Почти готово! Мы заметили, что вы создали ключ, но еще не подключились"
    - 24 часа после создания ключа: "Последний шанс активировать 3 дня бесплатного премиум-доступа"
    """
    now = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        # Триггер 1: 15 минут
        time_15m_ago = now - timedelta(minutes=15)
        time_14m_ago = now - timedelta(minutes=14)

        query_15m = (
            select(User)
            .join(Subscription)
            .where(
                Subscription.is_active == True,
                Subscription.plan_type == "trial",
                User.key_created_at >= time_14m_ago,
                User.key_created_at <= time_15m_ago,
                User.notified_inactive_15m == False,
                User.notified_inactive_3h == False,
                User.notified_inactive_24h == False,
            )
        )

        result_15m = await session.execute(query_15m)
        users_15m = result_15m.scalars().all()

        for user in users_15m:
            try:
                message_text = (
                    f"{hbold('🔑 Твой персональный ключ Onyx VPN зарезервирован')}\n\n"
                    f"Ключ ждёт подключения. Нужна помощь?\n\n"
                    f"✨ OnyxVpn — свобода без ограничений"
                )

                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📘 Пошаговая инструкция",
                                web_app={"url": f"{settings.webapp_url}?step=connect"},
                            )
                        ]
                    ]
                )

                await bot.send_message(
                    chat_id=user.tg_id,
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )

                user.notified_inactive_15m = True
                await session.commit()

                logger.info("Отправлено уведомление 15 мин: user_id=%s", user.tg_id)

            except Exception as e:
                logger.error("Ошибка отправки уведомления 15 мин пользователю %s: %s", user.tg_id, e)
                continue

        # Триггер 2: 3 часа
        time_3h_ago = now - timedelta(hours=3)
        time_2h59m_ago = now - timedelta(hours=2, minutes=59)

        query_3h = (
            select(User)
            .join(Subscription)
            .where(
                Subscription.is_active == True,
                Subscription.plan_type == "trial",
                User.key_created_at >= time_3h_ago,
                User.key_created_at <= time_2h59m_ago,
                User.notified_inactive_3h == False,
                User.notified_inactive_24h == False,
            )
        )

        result_3h = await session.execute(query_3h)
        users_3h = result_3h.scalars().all()

        for user in users_3h:
            try:
                message_text = (
                    f"{hbold('⚡️ Почти готово!')}\n\n"
                    f"Мы заметили, что вы создали ключ, но еще не подключились.\n\n"
                    f"Без VPN ваши данные в публичных Wi-Fi сетях уязвимы.\n"
                    f"Защитите себя в 1 клик.\n\n"
                    f"✨ OnyxVpn — ваш надёжный VPN"
                )

                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="⚡️ Подключить Onyx VPN",
                                web_app={"url": settings.webapp_url},
                            )
                        ]
                    ]
                )

                await bot.send_message(
                    chat_id=user.tg_id,
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )

                user.notified_inactive_3h = True
                await session.commit()

                logger.info("Отправлено уведомление 3 часа: user_id=%s", user.tg_id)

            except Exception as e:
                logger.error("Ошибка отправки уведомления 3 часа пользователю %s: %s", user.tg_id, e)
                continue

        # Триггер 3: 24 часа
        time_24h_ago = now - timedelta(hours=24)
        time_23h59m_ago = now - timedelta(hours=23, minutes=59)

        query_24h = (
            select(User)
            .join(Subscription)
            .where(
                Subscription.is_active == True,
                Subscription.plan_type == "trial",
                User.key_created_at >= time_24h_ago,
                User.key_created_at <= time_23h59m_ago,
                User.notified_inactive_24h == False,
            )
        )

        result_24h = await session.execute(query_24h)
        users_24h = result_24h.scalars().all()

        for user in users_24h:
            try:
                message_text = (
                    f"{hbold('🎁 Последний шанс!')}\n\n"
                    f"Активируйте 3 дня бесплатного премиум-доступа.\n\n"
                    f"Завтра бронь ключа аннулируется.\n\n"
                    f"✨ OnyxVpn — свобода без ограничений"
                )

                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🎁 Активировать бесплатно",
                                web_app={"url": f"{settings.webapp_url}?step=connect"},
                            )
                        ]
                    ]
                )

                await bot.send_message(
                    chat_id=user.tg_id,
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )

                user.notified_inactive_24h = True
                await session.commit()

                logger.info("Отправлено уведомление 24 часа: user_id=%s", user.tg_id)

            except Exception as e:
                logger.error("Ошибка отправки уведомления 24 часа пользователю %s: %s", user.tg_id, e)
                continue


async def start_notification_scheduler(bot: Bot) -> AsyncIOScheduler:
    """
    Запустить планировщик уведомлений.

    Создаёт и запускает APScheduler с задачами:
    1. Проверка уведомлений за 24 часа (каждую минуту)
    2. Проверка уведомлений за 1 час (каждую минуту)
    3. Очистка истёкших подписок (каждую минуту)
    4. Уведомления о неактивных ключах (каждую минуту)

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

    # Задача 4: Уведомления о неактивных ключах
    scheduler.add_job(
        send_inactive_key_notifications,
        trigger="interval",
        minutes=1,
        args=[bot],
        id="inactive_key_notifications",
        name="Inactive key notifications",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Планировщик уведомлений запущен")

    return scheduler
