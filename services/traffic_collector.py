"""Сборщик трафика WireGuard из Amnezia-контейнера.

Периодически (раз в N секунд) выполняет `wg show awg0` внутри контейнера
AmneziaWG, парсит вывод и обновляет поля total_bytes_received / total_bytes_sent
/ last_handshake_at у пользователей в БД.

Связь peer ↔ user: ключ клиента (WireGuard public key) хранится в
Subscription.uuid. По нему находим подписку, через неё — пользователя.

Вывод `wg show awg0` имеет формат:
    peer: <base64_public_key>
      endpoint: <ip>:<port>
      allowed ips: 10.8.1.x/32
      latest handshake: 1 minute, 27 seconds ago
      transfer: 1.23 GiB received, 456.78 MiB sent
      persistent keepalive: every 25 seconds

Парсинг построчный: начинаем блок peer на строке с префиксом "peer:",
внутри блока ищем "latest handshake:" и "transfer:".

Edge cases:
- Контейнер недоступен → логируем, возвращаемся без изменений, следующий
  проход через interval попробует снова.
- wg show вернул пустой вывод → нет ни одного peer, ничего не обновляем.
- Peer не найден в БД (например, ключ в awg0.conf остался от удалённого юзера)
  → пропускаем, не падаем.
- Парсинг числа провалился → пропускаем peer, остальные обрабатываем.
"""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Subscription, User
from services.amnezia import _exec_in_container

logger = logging.getLogger(__name__)


# Команда внутри контейнера. Используем `wg show awg0 dump` для машинно-читаемого
# формата (табуляция, по 8 полей на peer):
#   <public_key>\t<preshared_key>\t<endpoint>\t<allowed_ips>\t
#   <latest_handshake_unix>\t<transfer_rx>\t<transfer_tx>\t<persistent_keepalive>
# `dump` стабильнее парсить, чем текстовый `wg show` с локализованными строками.
WG_SHOW_COMMAND = "wg show awg0 dump"


# WireGuard считает transfer в байтах. Для отображения используем эти множители.
_KB = 1024
_MB = _KB * 1024
_GB = _MB * 1024
_TB = _GB * 1024


def format_bytes(num_bytes: int) -> str:
    """Форматирует количество байт в человекочитаемую строку (1024-based).

    Примеры:
        0         -> "0 B"
        512       -> "512 B"
        1536      -> "1.5 KB"
        1234567   -> "1.2 MB"
        5368709120 -> "5.0 GB"
    """
    if num_bytes is None or num_bytes < 0:
        return "—"
    if num_bytes < _KB:
        return f"{num_bytes} B"
    if num_bytes < _MB:
        return f"{num_bytes / _KB:.1f} KB"
    if num_bytes < _GB:
        return f"{num_bytes / _MB:.1f} MB"
    if num_bytes < _TB:
        return f"{num_bytes / _GB:.2f} GB"
    return f"{num_bytes / _TB:.2f} TB"


def _parse_wg_dump(output: str) -> list[dict]:
    """Парсит вывод `wg show awg0 dump`.

    Возвращает список словарей:
        {
            "public_key": str,
            "latest_handshake": datetime | None,  # UTC
            "bytes_received": int,
            "bytes_sent": int,
        }

    Peer без handshake (latest_handshake == 0) → latest_handshake = None.
    """
    peers: list[dict] = []
    now_unix = int(datetime.now(timezone.utc).timestamp())

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # dump-формат: поля разделены табами. Может быть 8 полей
        # (полный peer) или меньше, если что-то не задано.
        parts = line.split("\t")
        if len(parts) < 8:
            logger.debug("Пропускаю строку wg dump (мало полей): %s", line)
            continue

        public_key = parts[0]
        if not public_key:
            continue

        try:
            latest_handshake_unix = int(parts[4]) if parts[4] else 0
            transfer_rx = int(parts[5]) if parts[5] else 0
            transfer_tx = int(parts[6]) if parts[6] else 0
        except ValueError as e:
            logger.warning(
                "Не удалось распарсить числа wg dump для peer=%s...: %s. Строка: %s",
                public_key[:16], e, line,
            )
            continue

        # latest_handshake == 0 означает "никогда не подключался".
        # Если handshake был > 30 дней назад, тоже считаем отсутствующим —
        # иначе будет устаревшая активность в UI.
        latest_handshake: datetime | None = None
        if latest_handshake_unix > 0:
            age_sec = now_unix - latest_handshake_unix
            if 0 <= age_sec < 30 * 24 * 3600:
                latest_handshake = datetime.fromtimestamp(
                    latest_handshake_unix, tz=timezone.utc,
                )
            else:
                logger.debug(
                    "Peer %s... handshake %d сек назад — считаем отсутствующим",
                    public_key[:16], age_sec,
                )

        peers.append({
            "public_key": public_key,
            "latest_handshake": latest_handshake,
            "bytes_received": transfer_rx,
            "bytes_sent": transfer_tx,
        })

    return peers


async def _fetch_wg_peers() -> list[dict] | None:
    """Получает список peers из AmneziaWG-контейнера.

    Возвращает None при ошибке (контейнер недоступен, таймаут, невалидный вывод).
    Пустой список [] если wg show отработал, но peer'ов нет.
    """
    rc, stdout, stderr = await _exec_in_container(
        WG_SHOW_COMMAND, command_kind="wg_show",
    )

    if rc != 0:
        logger.error(
            "wg show в контейнере завершился с ошибкой (rc=%s): %s",
            rc, stderr[:500] if stderr else "no stderr",
        )
        return None

    if not stdout:
        logger.info("wg show вернул пустой вывод — нет ни одного peer")
        return []

    try:
        return _parse_wg_dump(stdout)
    except Exception as e:
        logger.exception("Неожиданная ошибка парсинга wg dump: %s", e)
        return None


async def collect_traffic_stats(session: AsyncSession) -> dict:
    """Собирает трафик из Amnezia и обновляет поля в User.

    Возвращает статистику выполнения:
        {
            "container_available": bool,
            "peers_seen": int,
            "users_updated": int,
            "users_unknown": int,  # peer в wg, но нет в БД
        }

    Идемпотентно: повторный вызов просто перезаписывает поля актуальными
    значениями из wg show. WireGuard — кумулятивный счётчик, поэтому
    значения всегда растут, но это нормально (мы храним total).
    """
    peers = await _fetch_wg_peers()
    if peers is None:
        return {
            "container_available": False,
            "peers_seen": 0,
            "users_updated": 0,
            "users_unknown": 0,
        }

    if not peers:
        return {
            "container_available": True,
            "peers_seen": 0,
            "users_updated": 0,
            "users_unknown": 0,
        }

    # Строим map public_key → peer_data для быстрого поиска
    peer_by_key = {p["public_key"]: p for p in peers}

    # Достаём из БД все активные подписки, у которых uuid встречается
    # в wg show (т.е. peer с этим ключом сейчас существует в Amnezia).
    # Один запрос вместо N: загружаем всех активных пользователей сразу.
    # selectinload(Subscription.user) нужен, чтобы User грузился сразу в том же
    # await — иначе доступ к sub.user ниже попытается лениво догрузить связь
    # синхронно и упадёт с MissingGreenlet в async-контексте.
    subs_q = (
        select(Subscription)
        .options(selectinload(Subscription.user))
        .where(Subscription.is_active == True)
    )
    result = await session.execute(subs_q)
    active_subs = result.scalars().all()

    updated = 0
    unknown = 0

    for sub in active_subs:
        peer = peer_by_key.get(sub.uuid)
        if peer is None:
            # Ключ есть в БД как активная подписка, но в wg show его нет.
            # Это нормальная ситуация во время revoke/reload — пропускаем.
            continue

        user = sub.user
        old_rx = user.total_bytes_received
        old_tx = user.total_bytes_sent

        # WireGuard cumulative: если wg показывает меньше, чем мы хранили
        # (например, peer был пересоздан), берём max, чтобы не "откатывать".
        user.total_bytes_received = max(old_rx, peer["bytes_received"])
        user.total_bytes_sent = max(old_tx, peer["bytes_sent"])
        user.last_handshake_at = peer["latest_handshake"]
        # Также обновляем общий last_activity_at — он используется в уведомлениях
        # о неактивности (см. bot/services/scheduler.py:notified_inactive_*).
        if peer["latest_handshake"] is not None:
            user.last_activity_at = peer["latest_handshake"]

        if (
            user.total_bytes_received != old_rx
            or user.total_bytes_sent != old_tx
            or user.last_handshake_at != peer["latest_handshake"]
        ):
            updated += 1

    unknown = sum(
        1 for p in peers if p["public_key"] not in {s.uuid for s in active_subs}
    )
    if unknown > 0:
        logger.warning(
            "В wg show %d peer'ов, для которых нет активной подписки в БД",
            unknown,
        )

    await session.commit()

    logger.info(
        "Трафик собран: peers=%d, обновлено=%d, неизвестных=%d",
        len(peers), updated, unknown,
    )

    return {
        "container_available": True,
        "peers_seen": len(peers),
        "users_updated": updated,
        "users_unknown": unknown,
    }


async def get_user_traffic(session: AsyncSession, tg_id: int) -> dict | None:
    """Возвращает трафик конкретного пользователя для UI админки.

    None если пользователь не найден.
    """
    user_q = select(User).where(User.tg_id == tg_id)
    user = (await session.execute(user_q)).scalar_one_or_none()
    if user is None:
        return None

    # Достаём подписку (активную или последнюю) для дополнительных полей
    sub_q = (
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub = (await session.execute(sub_q)).scalar_one_or_none()

    return {
        "tg_id": user.tg_id,
        "username": user.username,
        "total_bytes_received": user.total_bytes_received,
        "total_bytes_sent": user.total_bytes_sent,
        "last_handshake_at": (
            user.last_handshake_at.isoformat() if user.last_handshake_at else None
        ),
        "last_activity_at": (
            user.last_activity_at.isoformat() if user.last_activity_at else None
        ),
        "subscription_active": sub.is_active if sub else False,
        "subscription_expires_at": (
            sub.expires_at.isoformat() if sub and sub.expires_at else None
        ),
        "subscription_plan_type": sub.plan_type if sub else None,
    }
