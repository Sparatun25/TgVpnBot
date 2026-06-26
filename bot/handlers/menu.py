"""Инлайн-меню бота: профиль, подписка, управление VPN.

Callback-хендлеры редактируют исходное сообщение /start на месте — чат
остаётся чистым, без каши из новых сообщений. Если редактирование
провалилось (например, сообщение старше 48 часов — Telegram запрещает
edit), отправляем новое сообщение с тем же контентом.
"""

import asyncio
import html
import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.utils.markdown import hbold
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from bot.utils import build_referral_link, build_referral_share_url
from core.config import settings
from core.db import async_session_factory
from database.models import PlanType, Subscription, User

logger = logging.getLogger(__name__)

router = Router()

# Человекочитаемые имена планов. Должны совпадать с тем, что мы
# показываем в Mini App — иначе юзер запутается между ботом и приложением.
PLAN_DISPLAY_NAMES = {
    PlanType.TRIAL: "Триал",
    PlanType.MONTHLY: "Месяц",
    PlanType.QUARTER: "Квартал",
    PlanType.YEAR: "Год",
}

# Callback data ограничен 64 байтами. Наши идентификаторы короче 32 — есть запас.
CB_MAIN = "menu:main"
CB_PROFILE = "menu:profile"
CB_SUBSCRIPTION = "menu:subscription"
CB_VPN = "menu:vpn"

# Таймаут на загрузку профиля. Без него зависший пул / сеть оставит
# callback без ответа — спиннер у юзера крутится вечно, а ответ
# TelegramAPIError «query is too old» прилетит через минуту.
DB_QUERY_TIMEOUT_SEC = 10


def _format_balance(kopecks: int) -> str:
    """Баланс из копеек в рубли с двумя знаками после запятой."""
    rubles = kopecks / 100
    return f"{rubles:.2f} ₽"


def _format_traffic(received: int, sent: int) -> str:
    """Суммарный трафик (received + sent) в человекочитаемом виде.

    Лимит не показываем — в БД нет per-plan ограничения трафика, поэтому
    пишем «Безлимит». Если когда-нибудь добавим лимиты — вынести в
    отдельный столбец и прокинуть сюда.
    """
    total = received + sent
    if total == 0:
        return "Нет трафика"
    if total < 1024:
        return f"{total} Б"
    if total < 1024 * 1024:
        return f"{total / 1024:.1f} КБ"
    if total < 1024 * 1024 * 1024:
        return f"{total / (1024 * 1024):.1f} МБ"
    return f"{total / (1024 * 1024 * 1024):.2f} ГБ"


def _format_days_left(expires_at: datetime) -> str:
    """Сколько осталось до окончания подписки.

    Возвращает:
        «N дн» — больше суток,
        «Истекает сегодня» — последние 24 часа,
        «Истекает через N ч» — последние часы,
        «Истекла» — просрочена.
    """
    now = datetime.now(timezone.utc)
    # expires_at из БД всегда tz-aware (DateTime(timezone=True)),
    # но на старых записях может прийти naive — нормализуем.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    delta = expires_at - now
    if delta.total_seconds() <= 0:
        return "Истекла"
    days = delta.days
    if days >= 1:
        return f"{days} дн"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"Истекает через {hours} ч"
    minutes = (delta.seconds % 3600) // 60
    return f"Истекает через {minutes} мин" if minutes > 0 else "Истекает сейчас"


def _days_left_with_icon(days_text: str) -> str:
    """Префиксует «Осталось» эмодзи по срочности.

    Логика общая для профиля и раздела «Подписка»:
    - «Истекла» / «Истекает…» → ⚠️ (критично)
    - ≤7 дней → ⏳ (скоро истекает)
    - иначе → 📅 (штатно, всё спокойно)

    Возвращает «<emoji> <days_text>» — готово к подстановке в строку
    после f"{hbold('Осталось')}: ".
    """
    if "Истекает" in days_text or days_text == "Истекла":
        return f"⚠️ {days_text}"
    if days_text.endswith(" дн"):
        try:
            n = int(days_text.split()[0])
        except (ValueError, IndexError):
            n = 999
        if n <= 7:
            return f"⏳ {days_text}"
    return f"📅 {days_text}"


def _format_last_handshake(last_handshake_at: datetime | None) -> str:
    """Когда юзер последний раз коннектился к VPN.

    NULL = ключ есть, но коннекта ещё не было. Дельта в будущем —
    защита от clock skew между ботом и сборщиком трафика (см.
    services/traffic_collector.py).
    """
    if last_handshake_at is None:
        return "не было"
    if last_handshake_at.tzinfo is None:
        last_handshake_at = last_handshake_at.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - last_handshake_at
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "не было"
    if seconds < 60:
        return "только что"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин назад"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ч назад"
    days = delta.days
    return f"{days} дн назад"


async def _load_profile_data(tg_id: int) -> tuple[User | None, Subscription | None, int]:
    """Загружает пользователя, активную подписку и количество рефералов.

    Returns:
        (user, active_subscription_or_None, referral_count).
        user может быть None, если /start не был вызван (теоретически —
        menu callbacks доступны только после /start).
    """
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        user = (
            await session.execute(select(User).where(User.tg_id == tg_id))
        ).scalar_one_or_none()
        if not user:
            return None, None, 0

        # Активная = is_active=True И ещё не истекла.
        # Если у юзера несколько подписок (например, продлил заранее),
        # берём ту, что истекает позже всех.
        sub = (
            await session.execute(
                select(Subscription)
                .where(
                    Subscription.user_id == user.id,
                    Subscription.is_active == True,
                    Subscription.expires_at > now,
                )
                .order_by(Subscription.expires_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        ref_count = (
            await session.execute(
                select(func.count(User.id)).where(User.referred_by_id == tg_id)
            )
        ).scalar_one()

        return user, sub, int(ref_count or 0)


async def _safe_load_profile(
    tg_id: int,
) -> tuple[User | None, Subscription | None, int] | None:
    """Загружает профиль с защитой от зависшего запроса и падения БД.

    Returns:
        (user, sub, ref_count) — то же, что и _load_profile_data.
        None — если БД не ответила за DB_QUERY_TIMEOUT_SEC или бросила
        SQLAlchemyError. Хендлер по None покажет алерт «Попробуйте позже»
        и не оставит спиннер крутиться.
    """
    try:
        return await asyncio.wait_for(
            _load_profile_data(tg_id), timeout=DB_QUERY_TIMEOUT_SEC
        )
    except asyncio.TimeoutError:
        logger.warning(
            "profile_load_timeout tg_id=%s timeout=%s",
            tg_id,
            DB_QUERY_TIMEOUT_SEC,
        )
        return None
    except SQLAlchemyError:
        logger.exception("profile_load_db_error tg_id=%s", tg_id)
        return None


def _build_profile_text(
    first_name: str,
    last_name: str,
    tg_id: int,
    user: User,
    sub: Subscription | None,
    ref_count: int,
    bot_username: str | None = None,
) -> str:
    """Собирает текст профиля для сообщения в Telegram."""
    # Имя и username приходят от Telegram. Перед подстановкой в HTML
    # обязательно escape — иначе Telegram отрендерит содержимое как теги
    # (например, имя `<b>hack</b>` сломает сообщение или хуже — пройдёт
    # как разметка). html.escape экранирует <, >, &, ", '.
    escaped_first = html.escape(first_name)
    escaped_last = html.escape(last_name)
    escaped_username = html.escape(user.username) if user.username else None

    full_name = " ".join(p for p in (escaped_first, escaped_last) if p).strip()
    if not full_name:
        full_name = f"@{escaped_username}" if escaped_username else "Без имени"

    lines: list[str] = [
        f"🐈 {hbold('Ваш профиль')}",
        "",
        f"👤 {hbold('Имя')}: {full_name}",
        f"🆔 {hbold('Telegram ID')}: <code>{tg_id}</code>",
        f"💰 {hbold('Баланс')}: {_format_balance(user.balance)}",
        f"👥 {hbold('Рефералов')}: {ref_count}",
    ]

    if sub:
        plan_name = PLAN_DISPLAY_NAMES.get(sub.plan_type, sub.plan_type.value)
        lines.append(
            f"📡 {hbold('Подписка')}: {plan_name} — активна"
        )
        days_text = _days_left_with_icon(_format_days_left(sub.expires_at))
        lines.append(f"{hbold('Осталось')}: {days_text}")
    else:
        lines.append(f"📡 {hbold('Подписка')}: нет активной")

    traffic = _format_traffic(user.total_bytes_received, user.total_bytes_sent)
    lines.append(f"📊 {hbold('Трафик')}: {traffic} / безлимит")

    # Последний handshake — только при активной подписке. Без ключа
    # коннекта быть не может, и строка ввела бы в заблуждение («не было»
    # для юзера без подписки выглядит как баг, а не как «всё ок, ключа
    # ещё нет»). Полезно отделить «ключ работает, просто не использую»
    # от «ключ создали, но я его ни разу не вставлял в Amnezia».
    if sub:
        lines.append(
            f"🔌 {hbold('Подключение')}: {_format_last_handshake(user.last_handshake_at)}"
        )

    # Реферальная ссылка — отдельный блок, с пустой строкой-разделителем.
    # Показываем всегда (даже при 0 рефералов): кнопка «Поделиться» даёт
    # существующим юзерам доступ к шерингу, которого раньше не было.
    # bot_username может быть None — callback-путь его не пробрасывает,
    # тогда показываем только кол-во рефералов без URL.
    if bot_username:
        ref_link = build_referral_link(bot_username, tg_id)
        lines.append("")
        lines.append(f"🎁 {hbold('Ваша ссылка')}:")
        lines.append(f"<code>{html.escape(ref_link)}</code>")

    # CTA — отдельным блоком после данных, с пустой строкой-разделителем
    # и 👉-префиксом. Раньше стояло сразу под строкой подписки, и при
    # F-pattern сканировании сливалось со строкой трафика — юзер читал
    # как ещё одну data-row.
    if not sub:
        lines.append("")
        lines.append("👉 Откройте приложение — там 3 дня бесплатно без карты.")

    return "\n".join(lines)


def _build_profile_keyboard(
    has_active_sub: bool,
    tg_id: int,
    bot_username: str | None = None,
) -> InlineKeyboardMarkup:
    """Кнопки под профилем. Зависят от наличия активной подписки.

    Без подписки главная CTA — «🎁 Активировать 3 дня бесплатно»
    (deep-link в Mini App на экран тарифов). С подпиской — «🔐 Управление VPN»,
    потому что юзер уже подключён и хочет тюнить ключ/устройства.

    «Пополнить баланс» оставляем только в варианте без подписки (с активной
    юзер и так знает, что у него всё работает; баланс пополняется в
    Mini App).

    «📤 Поделиться» — в обоих вариантах: раньше шеринг был только в
    /start для новых юзеров, существующие не имели способа поделиться
    ссылкой, не залезая в БД руками.
    """
    if has_active_sub:
        rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    text="🔐 Управление VPN",
                    callback_data=CB_VPN,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚀 Открыть приложение",
                    web_app={"url": settings.webapp_url},
                )
            ],
        ]
    else:
        rows = [
            [
                # Без deep-link: открываем Mini App «как есть», чтобы новый
                # юзер увидел WelcomeScreen с котиком и CTA «Начать бесплатно».
                # Раньше тут был `?screen=tariffs` — App.tsx по этому флагу
                # принудительно прыгал на step='dashboard', и онбординг
                # (welcome → install → preparing → success) полностью
                # скипался: юзер оказывался на тарифах в дашборде без
                # приветственного брендового экрана.
                # Если юзер уже использовал триал — loadProfile в App.tsx
                # сам перенаправит его на dashboard по has_used_trial=true.
                InlineKeyboardButton(
                    text="🎁 Активировать 3 дня бесплатно",
                    web_app={"url": settings.webapp_url},
                )
            ],
            [
                # Без deep-link: см. аналогичный комментарий у кнопки
                # «Активировать 3 дня бесплатно». Новый юзер должен сначала
                # попасть на WelcomeScreen, а не на пустую вкладку «Баланс»
                # в дашборде.
                InlineKeyboardButton(
                    text="💳 Пополнить баланс",
                    web_app={"url": settings.webapp_url},
                )
            ],
        ]

    # Кнопка «Поделиться» — общая для обеих веток. Если bot_username не
    # пришёл (теоретически — bot.get_me() упал), пропускаем кнопку,
    # но НЕ весь профиль: остальное остаётся работоспособным.
    if bot_username:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📤 Поделиться ссылкой",
                    url=build_referral_share_url(bot_username, tg_id),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="◀ Назад в меню",
                callback_data=CB_MAIN,
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_subscription_text(sub: Subscription | None) -> str:
    """Текст для раздела «Подписка» — короткий, чтобы помещался в экран.

    Термин унифицирован: «Подписка» для самой сущности везде —
    «Тарифы» остаётся только как название экрана-магазина в Mini App.
    """
    if not sub:
        return (
            f"⭐ {hbold('Подписка')}\n\n"
            "У вас пока нет активной подписки.\n\n"
            "В приложении доступны:\n"
            "• 3 дня бесплатно — без карты и SMS\n"
            "• Месяц, квартал, год — со скидкой за длительный период"
        )

    plan_name = PLAN_DISPLAY_NAMES.get(sub.plan_type, sub.plan_type.value)
    days_text = _days_left_with_icon(_format_days_left(sub.expires_at))
    return (
        f"⭐ {hbold('Подписка')}\n\n"
        f"📋 {hbold('Подписка')}: {plan_name}\n"
        f"{hbold('Осталось')}: {days_text}\n"
        f"📡 {hbold('Статус')}: активна"
    )


def _build_subscription_keyboard(sub: Subscription | None) -> InlineKeyboardMarkup:
    """Кнопки под разделом «Подписка». CTA зависит от состояния:

    - «Продлить» если подписка активна (есть что продлевать)
    - «Оформить» если нет (юзер будет покупать новую — слово «продлить»
      для него было бы неверным)
    """
    cta_text = "🚀 Продлить подписку" if sub else "🚀 Оформить подписку"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=cta_text,
                    web_app={"url": f"{settings.webapp_url}?screen=tariffs"},
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀ Назад в меню",
                    callback_data=CB_MAIN,
                )
            ],
        ]
    )


def _build_vpn_text(sub: Subscription | None) -> str:
    """Текст раздела «Управление VPN». State-aware:

    - Активная подписка — статус + отсылка к ключу в приложении.
      Юзер пришёл сюда проверить состояние или получить ключ, а не
      читать инструкцию по установке.
    - Без подписки — пошаговая инструкция установки AmneziaVPN.
    """
    if sub:
        plan_name = PLAN_DISPLAY_NAMES.get(sub.plan_type, sub.plan_type.value)
        days_text = _days_left_with_icon(_format_days_left(sub.expires_at))
        return (
            f"🔐 {hbold('Управление VPN')}\n\n"
            f"✅ Подписка активна — {plan_name}\n"
            f"{hbold('Осталось')}: {days_text}\n\n"
            f"Ключ и инструкция для вашего устройства — в приложении."
        )
    return (
        f"🔐 {hbold('Управление VPN')}\n\n"
        "Подключение за 3 шага:\n"
        "1️⃣ Установите AmneziaVPN (Play Market / App Store)\n"
        "2️⃣ Откройте приложение и выберите «Подключиться»\n"
        "3️⃣ Готово — защищённый интернет включён\n\n"
        "В приложении Onyx VPN вы получите персональный ключ."
    )


async def _safe_edit(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    """Редактирует сообщение или шлёт новое, если edit невозможен.

    Telegram запрещает редактировать сообщения старше 48 часов и сообщения
    в личке, если что-то ещё изменилось. В обоих случаях edit_text бросит
    TelegramAPIError — мы ловим и шлём новое сообщение, чтобы юзер всё равно
    увидел результат.
    """
    try:
        await callback.message.edit_text(
            text, reply_markup=reply_markup, parse_mode="HTML"
        )
    except TelegramAPIError as e:
        # «message is not modified» — текст совпадает. Не паникуем,
        # просто оставляем как есть.
        if "message is not modified" in str(e):
            return
        logger.warning(
            "edit_message_failed fallback_to_new: tg_id=%s error=%s",
            callback.from_user.id,
            e,
        )
        await callback.message.answer(
            text, reply_markup=reply_markup, parse_mode="HTML"
        )


@router.callback_query(F.data == CB_MAIN)
async def cb_back_to_main(callback: CallbackQuery) -> None:
    """Возврат в главное меню.

    Используем то же приветствие, что и в /start, но в редактируемом
    виде — без повторного создания записи в БД. Состояние (активная
    подписка / без) подгружаем, чтобы приветствие было релевантным.
    Если БД не ответила — fallback на нейтральный текст без has_active_sub,
    чтобы юзер не залип на спиннере.
    """
    from bot.handlers.start import build_main_menu_text, build_main_menu_keyboard

    first_name = (callback.from_user.first_name or "").strip()
    data = await _safe_load_profile(callback.from_user.id)
    has_active_sub = data is not None and data[1] is not None
    text = build_main_menu_text(
        first_name=first_name,
        has_active_sub=has_active_sub,
        is_new_user=False,
    )

    # get_me с таймаутом — консистентно с cb_show_profile. Если бот деградирован
    # / Telegram API моргнул — продолжаем без реферальной кнопки, основное
    # меню остаётся работоспособным.
    try:
        bot_me = await asyncio.wait_for(callback.bot.get_me(), timeout=5.0)
        bot_username = bot_me.username
    except (asyncio.TimeoutError, TelegramAPIError) as e:
        logger.warning(
            "back_to_main_get_me_failed tg_id=%s err=%s — показываем меню без реферальной ссылки",
            callback.from_user.id,
            e,
        )
        bot_username = None

    keyboard = build_main_menu_keyboard(
        tg_id=callback.from_user.id,
        bot_username=bot_username,
        is_new_user=False,
    )
    await _safe_edit(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == CB_PROFILE)
async def cb_show_profile(callback: CallbackQuery) -> None:
    """Показывает профиль пользователя inline (редактирует сообщение)."""
    tg_id = callback.from_user.id
    first_name = (callback.from_user.first_name or "").strip()
    last_name = (callback.from_user.last_name or "").strip()

    data = await _safe_load_profile(tg_id)
    if data is None:
        await callback.answer(
            "Не удалось загрузить профиль. Попробуйте позже.",
            show_alert=True,
        )
        return
    user, sub, ref_count = data
    if not user:
        # Юзер нажал кнопку до /start (например, через deep-link в callback).
        # Просим начать с /start — безопасно, идемпотентно.
        await callback.answer(
            "Сначала нажмите /start", show_alert=True
        )
        return

    # bot.get_me() нужен для реферальной ссылки и кнопки «Поделиться».
    # Если get_me упадёт (бот деградирован / Telegram API моргнул) —
    # продолжаем без ссылки, основной контент профиля остаётся.
    # 5-секундный таймаут: get_me обычно мгновенный, зависание = сеть
    # или rate-limit, и лучше показать профиль без шеринга, чем плодить
    # «query is too old» в логах.
    bot_username: str | None = None
    try:
        bot_me = await asyncio.wait_for(callback.bot.get_me(), timeout=5.0)
        bot_username = bot_me.username
    except (asyncio.TimeoutError, TelegramAPIError) as e:
        logger.warning(
            "profile_get_me_failed tg_id=%s err=%s — показываем профиль без реферальной ссылки",
            tg_id,
            e,
        )

    text = _build_profile_text(
        first_name, last_name, tg_id, user, sub, ref_count, bot_username
    )
    keyboard = _build_profile_keyboard(
        has_active_sub=sub is not None,
        tg_id=tg_id,
        bot_username=bot_username,
    )
    await _safe_edit(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == CB_SUBSCRIPTION)
async def cb_show_subscription(callback: CallbackQuery) -> None:
    """Показывает информацию о текущей подписке."""
    tg_id = callback.from_user.id
    data = await _safe_load_profile(tg_id)
    if data is None:
        await callback.answer(
            "Не удалось загрузить подписку. Попробуйте позже.",
            show_alert=True,
        )
        return
    _, sub, _ = data
    text = _build_subscription_text(sub)
    keyboard = _build_subscription_keyboard(sub)
    await _safe_edit(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == CB_VPN)
async def cb_show_vpn(callback: CallbackQuery) -> None:
    """Управление VPN. Текст зависит от наличия активной подписки —
    инструкция по установке для новичков, статус для подключённых.
    """
    data = await _safe_load_profile(callback.from_user.id)
    if data is None:
        await callback.answer(
            "Не удалось загрузить данные. Попробуйте позже.",
            show_alert=True,
        )
        return
    _, sub, _ = data
    text = _build_vpn_text(sub)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Открыть приложение",
                    web_app={"url": f"{settings.webapp_url}?step=connect"},
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀ Назад в меню",
                    callback_data=CB_MAIN,
                )
            ],
        ]
    )
    await _safe_edit(callback, text, keyboard)
    await callback.answer()
