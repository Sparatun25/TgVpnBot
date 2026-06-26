"""Помощники для построения реферальных ссылок и кнопок «Поделиться».

Источник правды для deep-link-формата и текста приглашения. Используется
и в /start (приветствие с кнопкой для новых юзеров), и в профиле
(для существующих юзеров). Если поменяется формат deep-link или
текст приглашения — менять тут.
"""

from urllib.parse import quote

# Текст, который Telegram подставит в поле сообщения при «Поделиться».
# Держим коротким: до 70 символов читается без обрезки на мобильных.
REFERRAL_INVITE_TEXT = (
    "Попробуй Onyx VPN — 3 дня бесплатно без карты"
)


def build_referral_link(bot_username: str, tg_id: int) -> str:
    """Ссылка для приглашения нового юзера.

    Deep-link вида `?start=ref_<tg_id>` обрабатывается в cmd_start
    (bot/handlers/start.py): referrer ищется по tg_id, а не по
    referral_code. Менять формат — только вместе с cmd_start, иначе
    старые приглашения перестанут работать.
    """
    return f"https://t.me/{bot_username}?start=ref_{tg_id}"


def build_referral_share_url(bot_username: str, tg_id: int) -> str:
    """URL для кнопки «Поделиться».

    Открывает диалог Telegram «Поделиться» с уже подставленным текстом.
    `quote(...)` нужен, потому что текст содержит пробелы и не-ASCII
    (без него Telegram получает битый URL и не подставляет текст).
    """
    link = build_referral_link(bot_username, tg_id)
    return (
        f"https://t.me/share/url?url={quote(link, safe='')}"
        f"&text={quote(REFERRAL_INVITE_TEXT, safe='')}"
    )
