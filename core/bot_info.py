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
import logging
import time

from aiogram import Bot

from core.config import settings

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 6 * 60 * 60
# Таймаут на getMe: Telegram API в норме отвечает за <1с. 5с — щедрый запас,
# но жёсткий предел, чтобы зависший сокет не блокировал /api/profile.
# Паттерн взят из bot/handlers/start.py:321.
_GETME_TIMEOUT_SECONDS = 5.0

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
            # asyncio.wait_for ОБЯЗАТЕЛЕН: без него зависший сокет к api.telegram.org
            # блокирует /api/profile до таймаута aiohttp (по дефолту 300с) — всё это
            # время Mini App показывает бесконечный лоадер. Штатный ответ getMe <1с,
            # 5с — щедрый запас. Таймаут бросает asyncio.TimeoutError, которое мы
            # ловим общим except Exception ниже — без finally сессия не закрылась бы.
            try:
                bot_info = await asyncio.wait_for(
                    bot.get_me(), timeout=_GETME_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Telegram getMe timeout (%sс) — вернуть stale-кэш",
                    _GETME_TIMEOUT_SECONDS,
                )
                return _cached_username

            _cached_username = bot_info.username
            _cached_at = time.monotonic()
            logger.info("bot_username обновлён: @%s", _cached_username)
            return _cached_username
        except Exception as e:
            # Сюда попадаем при сетевых ошибках, невалидном токене, проблемах
            # с JSON-ответом. Stale-кэш — лучше None: фронт просто отключит
            # кнопку копирования реферальной ссылки.
            logger.warning("Не удалось обновить bot_username: %s", e)
            return _cached_username
        finally:
            await bot.session.close()
