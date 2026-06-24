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
from database.models import User

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
            logger.info("Существующий пользователь: tg_id=%s", tg_id)

    # Формируем приветственное сообщение
    welcome_text = (
        f"{hbold('✨ Добро пожаловать в OnyxVpn!')}\n\n"
        f"{hitalic('Премиальный VPN для свободного интернета.')}\n\n"
        f"🔐 Безопасность и анонимность\n"
        f"⚡ Высокая скорость подключения\n"
        f"🎁 3 дня бесплатного доступа\n\n"
        f"Нажмите кнопку ниже, чтобы открыть приложение и активировать VPN."
    )

    # Создаём inline-кнопку с WebAppInfo
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Открыть OnyxVpn",
                    web_app={"url": settings.webapp_url},
                )
            ]
        ]
    )

    await message.answer(
        welcome_text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )
