"""Request-ID middleware + contextvars для сквозной корреляции логов.

Зачем: чтобы в логах можно было проследить конкретный HTTP-запрос
или Telegram update через всю цепочку вызовов (DB, Amnezia, payments, ...).

Реализация:
- ContextVar `request_id_var` хранит текущий request_id для текущего event loop.
- structlog.contextvars.merge_contextvars автоматически подхватывает значение
  ContextVar и добавляет в каждый лог (см. core/logging.py).
- RequestIdMiddleware (FastAPI/Starlette) на каждый HTTP-запрос:
  1. Берёт X-Request-ID из входящих headers, иначе генерирует uuid4.
  2. Кладёт в ContextVar (через token для корректного reset).
  3. Кладёт в request.state.request_id для хэндлеров.
  4. Добавляет X-Request-ID в response headers.
- bind_request_id_for_update() helper для aiogram-middleware (см. bot/main.py).

Использование в FastAPI (api/main.py):
    from core.middleware import RequestIdMiddleware
    app.add_middleware(RequestIdMiddleware)  # ПЕРВЫМ

Использование в aiogram (bot/main.py):
    from aiogram import BaseMiddleware
    from core.middleware import bind_request_id_for_update

    class UpdateContextMiddleware(BaseMiddleware):
        async def __call__(self, handler, event, data):
            with bind_request_id_for_update(event):
                return await handler(event, data)
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Singleton ContextVar: живёт в текущем asyncio.Task, автоматически
# скоупится при await. Нулевой стоимости вне request'а.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Размер UUID4 в hex: 32 символа. Достаточно для коллизий в пределах
# разумного timeframe (можно обрезать до 16 для компактности в логах).
REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Прокидывает X-Request-ID через всю цепочку обработки HTTP-запроса.

    Приоритет:
    1. Если клиент прислал X-Request-ID в headers — используем его (для
       сквозной трассировки между сервисами).
    2. Иначе генерируем новый uuid4.

    В обоих случаях ID прокидывается через:
    - request.state.request_id (для хэндлеров)
    - request_id_var ContextVar (для structlog-логов)
    - X-Request-ID в response headers (для клиента)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Берём существующий или генерируем новый.
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id

        # bind_contextvars пушит в ContextVar. Чтобы при завершении запроса
        # значение не утекло в следующий, нужен явный unbind в finally.
        structlog.contextvars.bind_contextvars(request_id=request_id)
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            # unbind сбрасывает наши bind'ы (только request_id/tg_id если мы их биндили)
            structlog.contextvars.unbind_contextvars("request_id")
            request_id_var.reset(token)

        # Добавляем в response headers (в т.ч. при ошибках).
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


@contextmanager
def bind_request_id_for_update(update) -> Iterator[str]:
    """Context-manager для aiogram: биндит request_id + tg_id/chat_id на время обработки Update.

    Использование в bot/main.py:

        class UpdateContextMiddleware(BaseMiddleware):
            async def __call__(self, handler, event, data):
                with bind_request_id_for_update(event):
                    return await handler(event, data)

    Почему context-manager, а не простой bind_contextvars:
    unbind_contextvars нужен для cleanup после update — иначе contextvars
    протекают между update'ами в event loop.
    """
    # Используем update_id как request_id: он уникален в пределах бота
    # и доступен во всех типах Update (Message, CallbackQuery, ...).
    update_id = getattr(update, "update_id", None)
    request_id = f"upd-{update_id}" if update_id is not None else uuid.uuid4().hex

    bind_kwargs: dict[str, str | int] = {"request_id": request_id}

    # tg_id доступен в большинстве update'ов: Message.from_user, CallbackQuery.from_user,
    # InlineQuery.from_user. Для Update без from_user (например, channel_post) — пропускаем.
    from_user = getattr(update, "from_user", None)
    if from_user is not None and getattr(from_user, "id", None) is not None:
        bind_kwargs["tg_id"] = from_user.id

    chat = getattr(update, "chat", None)
    if chat is not None and getattr(chat, "id", None) is not None:
        bind_kwargs["chat_id"] = chat.id

    structlog.contextvars.bind_contextvars(**bind_kwargs)
    try:
        yield request_id
    finally:
        # Сбрасываем именно наши ключи, чтобы не задеть чужие bind'ы.
        structlog.contextvars.unbind_contextvars(*bind_kwargs.keys())
