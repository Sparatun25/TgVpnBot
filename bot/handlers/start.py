"""Обработчик команды /start с поддержкой рефералов."""

import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.markdown import hbold, hitalic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import async_session_factory
from database.models import PlanType, Subscription, User

logger = logging.getLogger(__name__)

router = Router()


def _generate_referral_code(user_id: int) -> str:
    """Генерирует уникальный реферальный код для пользователя в формате base36."""
    chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    if user_id == 0:
        return 'ONYX0'
    result = ''
    n = user_id
    while n > 0:
        n, remainder = divmod(n, 36)
        result = chars[remainder] + result
    return f"ONYX{result}"


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandStart) -> None:
    """
    Обработчик команды /start.

    Приветствует пользователя, создаёт запись в БД если новый,
    обрабатывает реферальную ссылку, показывает кнопку открытия Mini App.
    """
    tg_id = message.from_user.id
    username = message.from_user.username
    args = command.args

    logger.info("Получена команда /start от пользователя %s", tg_id)

    async with async_session_factory() as session:
        # Проверяем, существует ли пользователь
        query = select(User).where(User.tg_id == tg_id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()

        # Для новых пользователей has_used_trial всегда False;
        # для существующих — перезаписывается ниже в else-ветке.
        has_used_trial = False

        if not user:
            # Новый пользователь — создаём запись
            user = User(
                tg_id=tg_id,
                username=username,
                balance=0,
                referral_code=_generate_referral_code(tg_id),
            )

            # Обрабатываем реферальный параметр
            if args and args.startswith("ref_"):
                try:
                    referrer_tg_id = int(args[4:])

                    # Проверяем, что пользователь не приглашает сам себя
                    if referrer_tg_id != tg_id:
                        # Проверяем, что пригласивший существует
                        referrer_query = select(User).where(User.tg_id == referrer_tg_id)
                        referrer_result = await session.execute(referrer_query)
                        referrer = referrer_result.scalar_one_or_none()

                        if referrer:
                            user.referred_by_id = referrer_tg_id
                            logger.info(
                                "Пользователь %s приглашён пользователем %s",
                                tg_id,
                                referrer_tg_id,
                            )
                        else:
                            logger.warning(
                                "Реферер %s не найден в БД",
                                referrer_tg_id,
                            )
                    else:
                        logger.warning("Пользователь %s пытался пригласить сам себя", tg_id)

                except ValueError:
                    logger.warning("Некорректный реферальный параметр: %s", args)

            session.add(user)
            await session.commit()
            logger.info("Создан новый пользователь: tg_id=%s", tg_id)

        else:
            # Проверяем, был ли у пользователя триал — определяет, какое приветствие показать.
            # Возвращающиеся юзеры с истёкшим триалом не должны видеть first-time копирайт
            # с кнопкой «3 дня бесплатно», как будто они тут впервые.
            # LIMIT 1 — нам нужен только факт наличия, не список подписок.
            trial_query = (
                select(Subscription.id)
                .where(
                    Subscription.user_id == user.id,
                    Subscription.plan_type == PlanType.TRIAL,
                )
                .limit(1)
            )
            trial_result = await session.execute(trial_query)
            has_used_trial = trial_result.scalar_one_or_none() is not None

            logger.info(
                "Существующий пользователь: tg_id=%s, has_used_trial=%s",
                tg_id,
                has_used_trial,
            )

    # Берём first_name для персонализации
    first_name = (message.from_user.first_name or "").strip()
    greeting = f", {hbold(first_name)}" if first_name else ""

    # «Новый» = не пришёл по рефералу И ни разу не активировал триал.
    # Раньше проверяли `user.balance == 0`, но это ломало кейс: юзер с
    # истёкшим триалом, без реферера и без денег на балансе получал
    # first-time приветствие с «3 дня бесплатно» как в свой первый визит.
    is_new_user = user.referred_by_id is None and not has_used_trial

    if is_new_user:
        # Полное приветствие для нового пользователя.
        # Структура: hook → ценность → CTA. Кот-талисман = наш бренд.
        welcome_text = (
            f"🐈‍⬛ {hbold('Onyx VPN')} — кот-защитник вашего интернета\n\n"
            f"Привет{greeting}! Я {hitalic('Onyx')} — VPN на&nbsp;AmneziaWG, "
            f"который реально обходит DPI и&nbsp;не&nbsp;ведёт логов.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{hbold('Что внутри')}\n\n"
            f"🔒 Шифрование AmneziaWG — обходит глубокий DPI\n"
            f"⚡️ Скорость до&nbsp;1&nbsp;Гбит/с без потерь\n"
            f"🌍 Серверы в&nbsp;Европе и&nbsp;Азии\n"
            f"🛡 Строгая политика no-logs\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎁 {hbold('3 дня бесплатно')} — без карты и&nbsp;смс.\n\n"
            f"Жмите кнопку ниже — заберёте персональный ключ за&nbsp;минуту."
        )
    else:
        # Короткое приветствие для возврата. Не грузим повторно onboarding-копирайт.
        welcome_text = (
            f"🐈‍⬛ С возвращением в&nbsp;{hbold('Onyx VPN')}{greeting}!\n\n"
            f"Ваш защищённый канал ждёт. Если триал закончился — "
            f"в&nbsp;приложении есть тарифы от&nbsp;99&nbsp;₽/мес."
        )

    # Кнопки: основная (открыть Mini App) + дополнительная (поделиться).
    # Реферальная ссылка помогает виральному росту — пользователь видит,
    # что может позвать друзей и получить бонус.
    bot_username = (await message.bot.get_me()).username
    referral_code = user.referral_code
    share_url = f"https://t.me/{bot_username}?start=ref_{tg_id}"

    buttons_row = [
        InlineKeyboardButton(
            text="🚀 Открыть Onyx VPN",
            web_app={"url": settings.webapp_url},
        )
    ]

    # Вторая кнопка только если есть что показать и это новый пользователь
    # (возвращающиеся уже знают про рефералку).
    if is_new_user and bot_username:
        buttons_row.append(
            InlineKeyboardButton(
                text="🎁 Пригласить друга",
                url=f"https://t.me/share/url?url={share_url}&text="
                    f"Попробуй Onyx VPN — 3 дня бесплатно без карты",
            )
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons_row])

    await message.answer(
        welcome_text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )
