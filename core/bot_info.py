"""Получает и кэширует username Telegram-бота для использования в API.

Кэш обновляется каждые 6 часов, чтобы:
- при холодном старте не делать N вызовов getMe (1 запрос на 1 воркер);
- при смене username через @BotFather подхватилось максимум через 6 часов;
- падение Telegram API не валило запрос — возвращаем stale-кэш.

Каждый FastAPI worker (их 4 в проде) держит СВОЙ экземпляр кэша —
getMe дешёвый, и при смене username задержка в 6ч приемлема.

Используется в `api/routes.py:get_profile`, чтобы отдавать Mini App
актуальный bot_username для построения реферальной ссылки без хардкода.
"""

import asyncio
import time

from aiogram import Bot

from core.config import settings

_CACHE_TTL_SECONDS = 6 * 60 * 60

_cached_username: str | None = None
_cached_at: float = 0.0
_lock = asyncio.Lock()


async def get_bot_username() -> str | None:
    """Возвращает username бота (без префикса @) или None при сбое Telegram API.

    На холодном старте (первый вызов после рестарта воркера) делает
    один запрос getMe и кэширует результат на _CACHE_TTL_SECONDS.

    Stale-while-error: если Telegram API временно недоступен, а ранее
    username уже кэшировался — возвращаем устаревшее значение вместо None,
    чтобы Mini App продолжал работать при сетевых флуктуациях.
    """
    global _cached_username, _cached_at

    if _cached_username is not None and (time.monotonic() - _cached_at) < _CACHE_TTL_SECONDS:
        return _cached_username

    async with _lock:
        if _cached_username is not None and (time.monotonic() - _cached_at) < _CACHE_TTL_SECONDS:
            return _cached_username

        bot = Bot(token=settings.bot_token.get_secret_value())
        try:
            bot_info = await bot.get_me()
            _cached_username = bot_info.username
            _cached_at = time.monotonic()
            return _cached_username
        except Exception:
            return _cached_username
        finally:
            await bot.session.close()
