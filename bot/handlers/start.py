"""Обработчик команды /start с поддержкой рефералов."""

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.markdown import hbold
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from bot.handlers.menu import CB_PROFILE, CB_SUBSCRIPTION, CB_VPN
from bot.utils import build_referral_share_url
from core.config import settings
from core.db import async_session_factory
from database.models import PlanType, Subscription, User

# Таймаут на операции с БД в /start. Без него зависший пул / сеть оставит
# юзера без ответа — Telegram покажет «typing...», а сообщение не придёт.
# Совпадает с DB_QUERY_TIMEOUT_SEC в menu.py — единый бюджет ожидания.
DB_QUERY_TIMEOUT_SEC = 10

logger = logging.getLogger(__name__)

router = Router()

# Текст главного меню используется и в /start, и в callback «Назад в меню»
# из menu.py. Держим один источник правды.
SUPPORT_URL = "https://t.me/OnyxVpnSupport"


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


def build_main_menu_text(
    first_name: str = "",
    has_active_sub: bool = False,
    is_new_user: bool = False,
) -> str:
    """Текст главного меню. Зависит от состояния юзера:

    - is_new_user=True: первый визит, тёплое приветствие + «3 дня бесплатно»
    - has_active_sub=True: VPN уже работает, короткое подтверждение и отсылка
      к приложению для управления ключом
    - иначе (вернулся без подписки): мотивация подключиться снова

    Импортируется из menu.py для callback «Назад в меню» — один источник
    правды, чтобы текст не расходился между /start и инлайн-кнопкой.
    """
    greeting = f", {hbold(first_name)}" if first_name else ""

    if has_active_sub:
        body = (
            f"Рады видеть снова{greeting}! Ваш VPN на месте 🐾\n"
            f"Ключ, статус и настройки — в приложении."
        )
    elif is_new_user:
        body = (
            f"Привет{greeting}! Подключайтесь к защищённому интернету "
            f"в&nbsp;один клик — без логов и&nbsp;с&nbsp;обходом DPI.\n\n"
            f"3 дня бесплатно — без карты и SMS."
        )
    else:
        body = (
            f"С возвращением{greeting}! Подключайтесь к защищённому интернету "
            f"в&nbsp;один клик — без логов и&nbsp;с&nbsp;обходом DPI."
        )

    return (
        f"🐈 {hbold('Onyx VPN')} — кот-защитник вашего интернета\n\n"
        f"{body}"
    )


def build_main_menu_keyboard(
    tg_id: int,
    bot_username: str | None,
    is_new_user: bool,
) -> InlineKeyboardMarkup:
    """Клавиатура главного меню.

    Структура (как на референсе): главная CTA на всю ширину, затем ряд из
    двух кнопок, потом одиночные «Управление VPN» и «Поддержка». Приглашение
    друга — отдельной строкой, только для новых юзеров (возвращающиеся уже
    знают про рефералку).
    """
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="🚀 Открыть приложение",
                web_app={"url": settings.webapp_url},
            )
        ],
        [
            InlineKeyboardButton(
                text="👤 Профиль",
                callback_data=CB_PROFILE,
            ),
            InlineKeyboardButton(
                text="⭐ Подписка",
                callback_data=CB_SUBSCRIPTION,
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔐 Управление VPN",
                callback_data=CB_VPN,
            )
        ],
        [
            InlineKeyboardButton(
                text="🛟 Поддержка",
                url=SUPPORT_URL,
            )
        ],
    ]

    if is_new_user and bot_username:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🎁 Пригласить друга — месяц бесплатно",
                    url=build_referral_share_url(bot_username, tg_id),
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _load_start_context(
    tg_id: int,
    username: str | None,
    args: str | None,
) -> tuple[bool, bool]:
    """Загружает контекст для /start: создаёт юзера если нового, проверяет триал/подписку.

    Returns:
        (is_new_user, has_active_sub) — нужно для state-aware приветствия.

    is_new_user = «первый визит без реферала и без триала». Используется для
    выбора копирайта («3 дня бесплатно» vs «Рады видеть снова»).

    Возвращает bool-ы (не ORM-объекты), чтобы caller не ловил
    DetachedInstanceError после закрытия сессии.
    """
    async with async_session_factory() as session:
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
            # Новый юзер только что создан — подписки физически быть не может.
            return True, False

        # Существующий пользователь.
        # Триал: проверяем факт наличия (LIMIT 1). Возвращающиеся юзеры с
        # истёкшим триалом не должны видеть first-time копирайт.
        trial_query = (
            select(Subscription.id)
            .where(
                Subscription.user_id == user.id,
                Subscription.plan_type == PlanType.TRIAL,
            )
            .limit(1)
        )
        has_used_trial = (await session.execute(trial_query)).scalar_one_or_none() is not None

        # Активная подписка нужна для state-aware приветствия.
        now = datetime.now(timezone.utc)
        active_sub_query = (
            select(Subscription.id)
            .where(
                Subscription.user_id == user.id,
                Subscription.is_active == True,
                Subscription.expires_at > now,
            )
            .limit(1)
        )
        has_active_sub = (await session.execute(active_sub_query)).scalar_one_or_none() is not None

        # «Новый» = не пришёл по рефералу И ни разу не активировал триал.
        # Раньше проверяли `user.balance == 0`, но это ломало кейс: юзер с
        # истёкшим триалом, без реферера и без денег на балансе получал
        # first-time приветствие с «3 дня бесплатно» как в свой первый визит.
        is_new_user = user.referred_by_id is None and not has_used_trial

        logger.info(
            "Существующий пользователь: tg_id=%s, has_used_trial=%s, has_active_sub=%s",
            tg_id,
            has_used_trial,
            has_active_sub,
        )
        return is_new_user, has_active_sub


async def _safe_load_start_context(
    tg_id: int,
    username: str | None,
    args: str | None,
) -> tuple[bool, bool] | None:
    """Загружает контекст для /start с защитой от зависшего запроса и падения БД.

    None — если БД не ответила за DB_QUERY_TIMEOUT_SEC или бросила
    SQLAlchemyError. Хендлер по None покажет «Попробуйте позже» и не
    оставит юзера без ответа.
    """
    try:
        return await asyncio.wait_for(
            _load_start_context(tg_id, username, args),
            timeout=DB_QUERY_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "start_db_timeout tg_id=%s timeout=%s",
            tg_id,
            DB_QUERY_TIMEOUT_SEC,
        )
        return None
    except SQLAlchemyError:
        logger.exception("start_db_error tg_id=%s", tg_id)
        return None


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandStart) -> None:
    """Обработчик команды /start.

    Приветствует пользователя, создаёт запись в БД если новый,
    обрабатывает реферальную ссылку, показывает главное меню.
    """
    tg_id = message.from_user.id
    username = message.from_user.username
    args = command.args

    logger.info("Получена команда /start от пользователя %s", tg_id)

    # Индикатор «печатает...» пока обрабатываем запрос.
    # Если Telegram API моргнул — не критично, едем дальше.
    try:
        await message.bot.send_chat_action(chat_id=tg_id, action="typing")
    except Exception as e:
        logger.debug("start_send_chat_action_failed tg_id=%s err=%s", tg_id, e)

    result = await _safe_load_start_context(tg_id, username, args)
    if result is None:
        await message.answer(
            "Не удалось обработать запрос. Попробуйте позже.",
        )
        return
    is_new_user, has_active_sub = result

    first_name = (message.from_user.first_name or "").strip()
    text = build_main_menu_text(
        first_name=first_name,
        has_active_sub=has_active_sub,
        is_new_user=is_new_user,
    )

    # get_me с таймаутом — иначе зависший запрос к Telegram API оставит
    # юзера без ответа. 5 сек — get_me обычно мгновенный, зависание = сеть
    # или rate-limit, лучше показать меню без реферальной ссылки.
    try:
        bot_me = await asyncio.wait_for(message.bot.get_me(), timeout=5.0)
        bot_username = bot_me.username
    except (asyncio.TimeoutError, TelegramAPIError) as e:
        logger.warning(
            "start_get_me_failed tg_id=%s err=%s — показываем меню без реферальной ссылки",
            tg_id,
            e,
        )
        bot_username = None

    keyboard = build_main_menu_keyboard(
        tg_id=tg_id,
        bot_username=bot_username,
        is_new_user=is_new_user,
    )

    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )
