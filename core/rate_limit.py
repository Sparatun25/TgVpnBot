"""In-memory sliding-window rate limiter.

Лёгкая защита от перебора эндпоинтов без внешних зависимостей (Redis, slowapi).
Подходит для single-process деплоя. В multi-worker среде лимит действует на процесс,
поэтому фактический порог может быть выше заявленного в N раз (N = кол-во воркеров).
Для production-grade ограничений переходите на Redis-backed решение.
"""

import asyncio
import time
from collections import defaultdict, deque
from typing import Deque


class SlidingWindowRateLimiter:
    """Скользящее окно по числу событий на ключ.

    Пример:
        limiter = SlidingWindowRateLimiter(max_events=5, window_seconds=60)
        if not await limiter.allow(user_id):
            raise HTTPException(429, "Слишком много запросов")
    """

    def __init__(self, *, max_events: int, window_seconds: float) -> None:
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._max_events = max_events
        self._window = window_seconds
        self._buckets: dict[int, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: int, *, now: float | None = None) -> bool:
        """Возвращает True, если запрос под ключом `key` разрешён.

        Логика:
        1. Захватываем лок, чтобы concurrent-запросы не проскочили окно.
        2. Выкидываем из deque события старше window_seconds.
        3. Если размер < max_events — добавляем текущее время и возвращаем True.
        """
        ts = now if now is not None else time.monotonic()
        async with self._lock:
            bucket = self._buckets[key]
            cutoff = ts - self._window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._max_events:
                return False
            bucket.append(ts)
            return True

    async def reset(self, key: int) -> None:
        """Сбросить историю по ключу. Полезно для тестов."""
        async with self._lock:
            self._buckets.pop(key, None)

    def size(self, key: int) -> int:
        """Сколько событий сейчас в окне (без ленивой чистки)."""
        return len(self._buckets.get(key, ()))


# Готовый лимитер для /subscription/trial: 5 попыток в минуту на tg_id.
# Trial — операция одноразовая (см. проверку has_used_trial), лимит защищает от:
# - двойных кликов при флапающем соединении,
# - брутфорса с целью найти уязвимость,
# - нагрузки на Amnezia-контейнер (генерация ключа — дорогая операция).
trial_limiter = SlidingWindowRateLimiter(max_events=5, window_seconds=60.0)
