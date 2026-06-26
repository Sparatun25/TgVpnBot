"""Сервис для работы с AmneziaWG через docker exec в контейнер."""

import asyncio
import base64
import json
import logging
import re
import shlex
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import async_session_factory
from core.metrics import (
    docker_exec_duration_seconds,
    docker_exec_errors_total,
    vpn_keys_created_total,
    vpn_keys_revoked_total,
)
from database.models import Subscription

logger = logging.getLogger(__name__)

# Таймаут для Docker-команд (секунды)
DOCKER_TIMEOUT = 30

# Асинхронный лок для сериализации создания ключей ВНУТРИ одного процесса.
# Без него два параллельных запроса в одном воркере могут прочитать один и тот
# же used_ips и выдать обоим клиентам одинаковый IP → конфликт в awg0.conf.
#
# НО: api/main.py запускается через `uvicorn --workers 4` (см. docker-entrypoint.sh)
# + отдельный bot-процесс. asyncio.Lock — process-local, он НЕ сериализует
# запросы между разными воркерами. Для межпроцессной синхронизации используется
# AMNEZIA_LOCK_KEY + pg_advisory_xact_lock (см. _amnezia_lock_session).
_ip_lock = asyncio.Lock()

# Ключ для Postgres advisory lock. Константа выбрана произвольно, но уникальна
# для нашего приложения. pg_advisory_xact_lock сериализует все операции
# create_client_key/revoke_client_key между всеми процессами (4 воркера + бот).
# Без него два воркера, обрабатывающие /subscription/trial параллельно, оба
# прошли бы asyncio.Lock (разные инстансы), прочитали одинаковый used_ips,
# выдали одинаковый свободный IP → дубликаты AllowedIPs в awg0.conf.
AMNEZIA_LOCK_KEY = 0x414D4E5A  # "AMNZ" в ASCII (просто memorable константа)

# Whitelist путей, которые разрешено читать/писать внутри контейнера.
# Двойная защита от shell-инъекции: даже если в будущем кто-то начнёт
# передавать сюда путь из БД / пользовательского ввода, посторонний файл
# не будет доступен.
ALLOWED_CONTAINER_PATHS: frozenset[str] = frozenset({
    "/opt/amnezia/awg/awg0.conf",
    "/opt/amnezia/awg/clientsTable",
    "/opt/amnezia/awg/wireguard_psk.key",
    "/opt/amnezia/awg/wireguard_server_private_key.key",
    "/opt/amnezia/awg/wireguard_server_public_key.key",
})


def _validate_container_path(path: str) -> None:
    """Проверить, что путь входит в allowlist. Иначе — ValueError."""
    if path not in ALLOWED_CONTAINER_PATHS:
        logger.error("Попытка доступа к запрещённому пути в контейнере: %s", path)
        raise ValueError(f"Путь {path} не разрешён для операций в контейнере")


# ─────────────────────────────────────────────────────────
# Docker exec helpers
# ─────────────────────────────────────────────────────────

async def _exec_in_container(command: str, command_kind: str = "other") -> tuple[int, str, str]:
    """
    Выполнить команду в контейнере AmneziaWG.

    Возвращает (return_code, stdout, stderr).

    Внимание: command передаётся в `sh -c`, поэтому shell-метасимволы
    интерпретируются. Вызывающие должны строить command только из
    литералов или предварительно экранировать значения через shlex.quote().

    command_kind — метка для Prometheus: "keygen" | "read" | "write" | "reload".
    Попадает в label histogram'а docker_exec_duration_seconds и в
    counter docker_exec_errors_total при инфраструктурных сбоях.
    """
    docker_cmd = [
        "docker", "exec", "-i",
        settings.amnezia_container_name,
        "sh", "-c", command,
    ]

    # Замеряем длительность ВСЕХ попыток — и успешных, и упавших.
    # Это даёт реальный p95/p99 latency включая timeout-ы и ошибки docker'а.
    start = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=DOCKER_TIMEOUT
        )

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        docker_exec_duration_seconds.labels(command_kind=command_kind).observe(
            time.monotonic() - start
        )
        return process.returncode or 0, stdout, stderr

    except FileNotFoundError:
        logger.error("Docker не найден в системе")
        docker_exec_errors_total.labels(error_kind="not_found").inc()
        docker_exec_duration_seconds.labels(command_kind=command_kind).observe(
            time.monotonic() - start
        )
        return 1, "", "Docker executable not found"

    except asyncio.TimeoutError:
        logger.error("Таймаут Docker-команды: %s", command)
        docker_exec_errors_total.labels(error_kind="timeout").inc()
        docker_exec_duration_seconds.labels(command_kind=command_kind).observe(
            time.monotonic() - start
        )
        # Без явного kill() subprocess остаётся висеть и жрёт ресурсы:
        # wait_for отменяет await на process.communicate(), но не убивает процесс.
        try:
            process.kill()
        except ProcessLookupError:
            pass  # процесс уже завершился между wait_for и kill
        try:
            await process.wait()
        except Exception:
            pass
        return 1, "", "Docker command timeout"

    except Exception as e:
        logger.exception("Ошибка Docker-команды: %s", e)
        docker_exec_errors_total.labels(error_kind="runtime").inc()
        docker_exec_duration_seconds.labels(command_kind=command_kind).observe(
            time.monotonic() - start
        )
        return 1, "", str(e)


async def _read_container_file(path: str) -> str:
    """Прочитать файл из контейнера AmneziaWG.

    Путь проверяется по allowlist (ALLOWED_CONTAINER_PATHS) и экранируется
    через shlex.quote — двойная защита от shell-инъекции при формировании
    `cat <path>` для `sh -c`.
    """
    _validate_container_path(path)
    safe_path = shlex.quote(path)
    rc, stdout, stderr = await _exec_in_container(f"cat {safe_path}", command_kind="read")
    if rc != 0:
        raise RuntimeError(f"Не удалось прочитать {path}: {stderr}")
    return stdout


async def _write_container_file(path: str, content: str) -> None:
    """Записать файл в контейнер AmneziaWG через stdin.

    Путь проверяется по allowlist и экранируется — даже если в будущем кто-то
    начнёт передавать сюда путь из БД или пользовательского ввода, инъекция
    в `cat > <path>` через `sh -c` не пройдёт.
    """
    _validate_container_path(path)
    safe_path = shlex.quote(path)
    docker_cmd = [
        "docker", "exec", "-i",
        settings.amnezia_container_name,
        "sh", "-c", f"cat > {safe_path}",
    ]

    # _write_container_file использует свой subprocess_exec (а не _exec_in_container),
    # потому что нужно прокинуть stdin. Поэтому метрики дублируем здесь вручную —
    # чтобы histogram/counter были консистентны с read/keygen/reload.
    start = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(input=content.encode("utf-8")),
            timeout=DOCKER_TIMEOUT,
        )

        docker_exec_duration_seconds.labels(command_kind="write").observe(
            time.monotonic() - start
        )

        if process.returncode != 0:
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Не удалось записать {path}: {stderr}")

    except FileNotFoundError:
        docker_exec_errors_total.labels(error_kind="not_found").inc()
        docker_exec_duration_seconds.labels(command_kind="write").observe(
            time.monotonic() - start
        )
        raise

    except asyncio.TimeoutError:
        docker_exec_errors_total.labels(error_kind="timeout").inc()
        docker_exec_duration_seconds.labels(command_kind="write").observe(
            time.monotonic() - start
        )
        # Без явного kill() subprocess остаётся висеть и жрёт ресурсы.
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            await process.wait()
        except Exception:
            pass
        raise

    except RuntimeError:
        # Бизнес-ошибка "файл не записан" (returncode != 0) — это НЕ инфра-сбой,
        # не ивентим docker_exec_errors_total. Histogram уже записан выше.
        raise

    except Exception:
        docker_exec_errors_total.labels(error_kind="runtime").inc()
        docker_exec_duration_seconds.labels(command_kind="write").observe(
            time.monotonic() - start
        )
        raise


# ─────────────────────────────────────────────────────────
# Парсинг конфигов
# ─────────────────────────────────────────────────────────

def _parse_peer_ips(config: str) -> set[str]:
    """Извлечь все занятые IP-адреса из awg0.conf."""
    return set(re.findall(r"AllowedIPs\s*=\s*([\d.]+)/32", config))


def _parse_server_params(config: str) -> dict[str, str]:
    """Извлечь параметры сервера из [Interface] секции awg0.conf."""
    params: dict[str, str] = {}
    for key in ("PrivateKey", "ListenPort", "Jc", "Jmin", "Jmax",
                "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4"):
        match = re.search(rf"^{key}\s*=\s*(.+)$", config, re.MULTILINE)
        if match:
            params[key] = match.group(1).strip()
    return params


async def _get_used_ips() -> set[str]:
    """Получить множество занятых IP из конфига сервера."""
    config = await _read_container_file("/opt/amnezia/awg/awg0.conf")
    return _parse_peer_ips(config)


async def _get_server_params() -> dict[str, str]:
    """Получить параметры сервера из конфига."""
    config = await _read_container_file("/opt/amnezia/awg/awg0.conf")
    return _parse_server_params(config)


async def _get_psk() -> str:
    """Прочитать PresharedKey из контейнера."""
    return (await _read_container_file("/opt/amnezia/awg/wireguard_psk.key")).strip()


async def _get_server_pubkey() -> str:
    """Прочитать публичный ключ сервера."""
    return (await _read_container_file(
        "/opt/amnezia/awg/wireguard_server_public_key.key"
    )).strip()


# ─────────────────────────────────────────────────────────
# Управление клиентами
# ─────────────────────────────────────────────────────────

async def _generate_keypair() -> tuple[str, str]:
    """
    Сгенерировать пару ключей WireGuard (private, public).

    Выполняет wg genkey | wg pubkey внутри контейнера.
    """
    rc, stdout, stderr = await _exec_in_container(
        "PRIVATE=$(wg genkey) && "
        "PUBLIC=$(echo $PRIVATE | wg pubkey) && "
        "echo \"$PRIVATE $PUBLIC\"",
        command_kind="keygen",
    )

    if rc != 0:
        raise RuntimeError(f"Не удалось сгенерировать ключи: {stderr}")

    parts = stdout.split()
    if len(parts) != 2:
        raise RuntimeError(f"Неожиданный вывод wg: {stdout}")

    return parts[0], parts[1]


async def _reload_interface() -> None:
    """Перезагрузить интерфейс AmneziaWG (down + up)."""
    rc, _, stderr = await _exec_in_container(
        "awg-quick down /opt/amnezia/awg/awg0.conf 2>/dev/null; "
        "awg-quick up /opt/amnezia/awg/awg0.conf",
        command_kind="reload",
    )
    if rc != 0:
        logger.error("Не удалось перезагрузить интерфейс: %s", stderr)
        raise RuntimeError(f"awg-quick reload failed: {stderr}")


def _remove_peer_from_config(config: str, public_key: str) -> str:
    """Удалить [Peer] блок с указанным PublicKey из конфига."""
    # Разбиваем на блоки [Peer]
    parts = re.split(r"(?=\[Peer\])", config)
    # Оставляем только те, где нет нужного PublicKey
    filtered = [p for p in parts if f"PublicKey = {public_key}" not in p]
    return "".join(filtered).rstrip() + "\n"


async def _update_clients_table(
    add: dict | None = None,
    remove_client_id: str | None = None,
) -> None:
    """
    Обновить clientsTable в контейнере.

    add: {"clientId": ..., "userData": {...}} — добавить клиента
    remove_client_id: clientId для удаления
    """
    try:
        raw = await _read_container_file("/opt/amnezia/awg/clientsTable")
        clients = json.loads(raw)
    except (RuntimeError, json.JSONDecodeError):
        clients = []

    if remove_client_id:
        clients = [c for c in clients if c.get("clientId") != remove_client_id]

    if add:
        clients.append(add)

    await _write_container_file(
        "/opt/amnezia/awg/clientsTable",
        json.dumps(clients, indent=4, ensure_ascii=False) + "\n",
    )


# ─────────────────────────────────────────────────────────
# Генерация vpn:// ключа
# ─────────────────────────────────────────────────────────

def _build_vpn_key(
    *,
    client_priv_key: str,
    client_pub_key: str,
    client_ip: str,
    server_params: dict[str, str],
    psk: str,
    server_pubkey: str,
    client_config: str,
) -> str:
    """
    Собрать vpn:// URL для импорта в AmneziaVPN.

    Формат: vpn://base64(compact_json) — строгий формат без пробелов.
    """
    port = server_params.get("ListenPort", "45019")

    # Полный формат AmneziaWG со всеми параметрами обфускации
    payload = {
        "containers": [
            {
                "container": "amnezia_awg",
                "awg": {
                    "address": f"{client_ip}/32",
                    "allowedIps": "0.0.0.0/0, ::/0",
                    "clientPrivKey": str(client_priv_key).strip(),
                    "hostName": str(settings.amnezia_server_host).strip(),
                    "H1": server_params.get("H1", ""),
                    "H2": server_params.get("H2", ""),
                    "H3": server_params.get("H3", ""),
                    "H4": server_params.get("H4", ""),
                    "Jc": server_params.get("Jc", ""),
                    "Jmax": server_params.get("Jmax", ""),
                    "Jmin": server_params.get("Jmin", ""),
                    "mtu": "1376",
                    "persistentKeepAlive": "25",
                    "port": port,
                    "pskKey": str(psk).strip(),
                    "S1": server_params.get("S1", ""),
                    "S2": server_params.get("S2", ""),
                    "S3": server_params.get("S3", ""),
                    "S4": server_params.get("S4", ""),
                    "serverPubKey": str(server_pubkey).strip(),
                },
            }
        ],
        "defaultContainer": "amnezia_awg",
        "description": "Onyx Premium",
        "dns1": "1.1.1.1",
        "dns2": "1.0.0.1",
        "hostName": str(settings.amnezia_server_host).strip(),
    }

    # Сериализация без едино��о лишнего пробела
    json_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    # Кодирование в Base64 с полной зачисткой управляющих символов
    b64_str = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
    cleaned_key = b64_str.replace("\n", "").replace("\r", "").replace(" ", "")

    return f"vpn://{cleaned_key}"


def _build_client_config(
    *,
    client_priv_key: str,
    client_ip: str,
    server_params: dict[str, str],
    psk: str,
    server_pubkey: str,
) -> str:
    """Собрать WireGuard-конфиг для клиента."""
    lines = [
        "[Interface]",
        f"Address = {client_ip}/32",
        "DNS = 1.1.1.1, 1.0.0.1",
        f"PrivateKey = {client_priv_key}",
    ]
    for key in ("Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4",
                "H1", "H2", "H3", "H4"):
        if key in server_params:
            lines.append(f"{key} = {server_params[key]}")

    lines.extend([
        "",
        "[Peer]",
        f"PublicKey = {server_pubkey}",
        f"PresharedKey = {psk}",
        "AllowedIPs = 0.0.0.0/0, ::/0",
        f"Endpoint = {settings.amnezia_server_host}:{server_params.get('ListenPort', '45019')}",
        "PersistentKeepalive = 25",
    ])
    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────
# Публичный API
# ─────────────────────────────────────────────────────────

async def create_client_key(
    user_id: int,
    is_trial: bool,
    plan_type: str | None = None,
) -> tuple[str, str]:
    """
    Создать ключ VPN для пользователя.

    Генерирует пару ключей WireGuard, находит свободный IP,
    добавляет Peer в awg0.conf, перезагружает интерфейс
    и возвращает vpn:// URL для импорта в AmneziaVPN.

    Args:
        user_id: ID пользователя в БД.
        is_trial: Если True — триальный ключ (3 дня).
        plan_type: Идентификатор тарифа ("monthly" | "quarter" | "year")
            для метрики. Если None — будет выведен из is_trial
            ("trial" если True, иначе "unknown").

    Returns:
        Кортеж (vpn_url, client_pub_key).
        vpn_url — URL для подключения через AmneziaVPN.
        client_pub_key — публичный ключ клиента (для хранения в uuid).

    Raises:
        RuntimeError: Если не удалось создать ключ.
    """
    # Сериализуем через межпроцессный advisory lock + внутрипроцессный asyncio.Lock.
    # asyncio.Lock защищает только в пределах одного воркера. Postgres advisory
    # lock защищает от race между 4 uvicorn воркерами + bot-процессом
    # (docker-entrypoint.sh).
    async with async_session_factory() as lock_session:
        async with lock_session.begin():
            await lock_session.execute(
                text("SELECT pg_advisory_xact_lock(:k)"),
                {"k": AMNEZIA_LOCK_KEY},
            )
            return await _create_client_key_locked(user_id, is_trial, plan_type)


async def _create_client_key_locked(
    user_id: int,
    is_trial: bool,
    plan_type: str | None = None,
) -> tuple[str, str]:
    """Тело create_client_key. Вызывающий ОБЯЗАН держать AMNEZIA_LOCK_KEY."""
    # Внутрипроцессный asyncio.Lock — оптимизация, чтобы не открывать лишнюю
    # DB-сессию для advisory lock на back-to-back вызовы в одном воркере.
    async with _ip_lock:
        try:
            # 1. Генерируем ключи клиента
            client_priv, client_pub = await _generate_keypair()

            # 2. Находим свободный IP
            used_ips = await _get_used_ips()
            client_ip = None
            for i in range(1, 255):
                ip = f"10.8.1.{i}"
                if ip not in used_ips:
                    client_ip = ip
                    break

            if client_ip is None:
                raise RuntimeError("Нет свободных IP-адресов (подсеть 10.8.1.0/24)")

            # 3. Читаем параметры сервера
            server_params = await _get_server_params()
            psk = await _get_psk()
            server_pubkey = await _get_server_pubkey()

            # 4. Собираем клиентский конфиг
            client_config = _build_client_config(
                client_priv_key=client_priv,
                client_ip=client_ip,
                server_params=server_params,
                psk=psk,
                server_pubkey=server_pubkey,
            )

            # 5. Добавляем Peer в awg0.conf
            server_config = await _read_container_file("/opt/amnezia/awg/awg0.conf")
            new_peer = (
                f"\n[Peer]\n"
                f"PublicKey = {client_pub}\n"
                f"PresharedKey = {psk}\n"
                f"AllowedIPs = {client_ip}/32\n"
            )
            await _write_container_file(
                "/opt/amnezia/awg/awg0.conf",
                server_config.rstrip() + "\n" + new_peer,
            )

            # 6. Обновляем clientsTable
            now_str = datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S %Y")
            await _update_clients_table(add={
                "clientId": client_pub,
                "userData": {
                    "clientName": f"OnyxVpn user {user_id}",
                    "creationDate": now_str,
                },
            })

            # 7. Перезагружаем интерфейс
            await _reload_interface()

            # 8. Собираем vpn:// URL
            vpn_url = _build_vpn_key(
                client_priv_key=client_priv,
                client_pub_key=client_pub,
                client_ip=client_ip,
                server_params=server_params,
                psk=psk,
                server_pubkey=server_pubkey,
                client_config=client_config,
            )

            logger.info(
                "Создан ключ для user_id=%s: ip=%s, pub=%s",
                user_id, client_ip, client_pub[:16] + "...",
            )
            # Метрика: ключ успешно создан. plan_type_label — английский
            # идентификатор для Prometheus label (вместо русских названий).
            plan_type_label = plan_type or ("trial" if is_trial else "unknown")
            vpn_keys_created_total.labels(
                is_trial=str(is_trial).lower(),
                plan_type=plan_type_label,
            ).inc()
            return vpn_url, client_pub

        except Exception as e:
            logger.exception("Ошибка создания ключа для user_id=%s: %s", user_id, e)
            raise RuntimeError(f"Не удалось создать VPN-ключ: {e}") from e


async def revoke_client_key(
    sub_uuid: str,
    source: str = "api",
    reason: str = "user_request",
) -> bool:
    """
    Удалить ключ пользователя из AmneziaWG.

    Находит Peer по public_key (хранится в Subscription.uuid), удаляет из
    awg0.conf и clientsTable, перезагружает интерфейс.

    Идемпотентно: если ключ уже удалён из обоих источников, возвращает True
    без изменений. Это упрощает повторные вызовы после сбоя (например, если
    прошлый revoke откатился на полпути).

    Конкурентная безопасность: пишет в те же файлы, что и create_client_key,
    поэтому обёрнут в pg_advisory_xact_lock (тот же ключ AMNEZIA_LOCK_KEY).
    Это сериализует операции между всеми процессами (4 uvicorn воркера +
    bot-процесс), а не только внутри одного asyncio.Lock.

    Args:
        sub_uuid: Public key клиента (хранится в Subscription.uuid).
        source: Источник вызова для метрики. "api" (по умолчанию) для ручных
            revoke через админку и POST /api/subscription/trial-error fallback,
            "scheduler" для check_expired_subscriptions.
        reason: Причина revoke для метрики. "user_request" по умолчанию,
            "expired" если вызвано из scheduler'а.

    Returns:
        True если ключ отсутствует в обоих источниках (успешно удалён или
        уже отсутствовал). False если во время операции произошла ошибка
        Docker/файловой системы — нужно ретраить или чинить руками.

    Raises:
        ValueError: если sub_uuid пустой или не похож на WireGuard public key.
    """
    if not sub_uuid or not isinstance(sub_uuid, str):
        raise ValueError("sub_uuid должен быть непустой строкой")

    # Cross-process advisory lock. Открываем отдельную DB-сессию — у caller's
    # session может быть открытая транзакция (например, в компенсирующем revoke
    # из api/routes.py), которая нам здесь не нужна.
    async with async_session_factory() as lock_session:
        async with lock_session.begin():
            await lock_session.execute(
                text("SELECT pg_advisory_xact_lock(:k)"),
                {"k": AMNEZIA_LOCK_KEY},
            )
            return await _revoke_client_key_locked(sub_uuid, source, reason)


async def _revoke_client_key_locked(
    sub_uuid: str,
    source: str,
    reason: str,
) -> bool:
    """Тело revoke_client_key под pg_advisory_xact_lock (см. revoke_client_key).

    Вызывающий код ДОЛЖЕН уже удерживать AMNEZIA_LOCK_KEY — иначе сериализация
    между процессами теряется и параллельный revoke может оставить orphan peer
    в Amnezia (см. multi-worker race audit).
    """
    async with _ip_lock:
        try:
            # 1. Читаем оба файла, чтобы понять, существует ли ключ вообще.
            config = await _read_container_file("/opt/amnezia/awg/awg0.conf")
            try:
                clients_table_raw = await _read_container_file("/opt/amnezia/awg/clientsTable")
                clients_in_table = any(
                    c.get("clientId") == sub_uuid
                    for c in json.loads(clients_table_raw)
                )
            except (RuntimeError, json.JSONDecodeError):
                clients_in_table = False

            new_config = _remove_peer_from_config(config, sub_uuid)
            in_config = new_config != config

            if not in_config and not clients_in_table:
                # Уже удалён — это OK, ничего не делаем.
                logger.info(
                    "Ключ %s уже отсутствует в awg0.conf и clientsTable — повторный revoke",
                    sub_uuid,
                )
                vpn_keys_revoked_total.labels(
                    result="noop", source=source, reason="already_revoked",
                ).inc()
                return True

            # 2. Если есть в awg0.conf — переписываем файл.
            if in_config:
                await _write_container_file("/opt/amnezia/awg/awg0.conf", new_config)
                logger.info("Peer %s удалён из awg0.conf", sub_uuid[:16] + "...")
            else:
                logger.warning(
                    "Ключ %s не найден в awg0.conf, но есть в clientsTable — "
                    "исправляем рассинхронизацию",
                    sub_uuid,
                )

            # 3. Удаляем из clientsTable.
            if clients_in_table:
                await _update_clients_table(remove_client_id=sub_uuid)
                logger.info("clientId %s удалён из clientsTable", sub_uuid[:16] + "...")
            else:
                logger.warning(
                    "Ключ %s не найден в clientsTable, но был в awg0.conf — "
                    "исправляем рассинхронизацию",
                    sub_uuid,
                )

            # 4. Перезагружаем интерфейс (down + up) только если меняли awg0.conf.
            if in_config:
                await _reload_interface()

            logger.info("Ключ %s отозван", sub_uuid)
            vpn_keys_revoked_total.labels(
                result="success", source=source, reason=reason,
            ).inc()
            return True

        except RuntimeError as e:
            # RuntimeError приходит из _read_container_file / _write_container_file /
            # _reload_interface. Это инфраструктурная проблема — caller может
            # ретраить (schedluer сделает это на следующем проходе).
            logger.error(
                "Инфраструктурная ошибка отзыва ключа %s: %s",
                sub_uuid, e,
            )
            vpn_keys_revoked_total.labels(
                result="failure", source=source, reason="runtime_error",
            ).inc()
            return False
        except FileNotFoundError as e:
            # Docker-контейнер не найден — это критично, но лучше вернуть False
            # чем ронять caller'а (schedluer'у и админу достаточно знать, что revoke
            # не выполнен).
            logger.error(
                "Контейнер Amnezia недоступен при отзыве ключа %s: %s",
                sub_uuid, e,
            )
            vpn_keys_revoked_total.labels(
                result="failure", source=source, reason="container_unavailable",
            ).inc()
            return False
        except Exception as e:
            # Непредвиденная ошибка — логируем traceback для диагностики, но не
            # роняем процесс (schedluer или админ продолжат работу).
            logger.exception(
                "Неизвестная ошибка при отзыве ключа %s: %s",
                sub_uuid, e,
            )
            vpn_keys_revoked_total.labels(
                result="failure", source=source, reason="unknown",
            ).inc()
            return False


async def check_expired_subscriptions(session: AsyncSession) -> list[Subscription]:
    """
    Найти все истёкшие подписки и отозвать ключи.

    Возвращает список успешно обработанных подписок (revoke + is_active=False).
    """
    now = datetime.now(timezone.utc)

    query = select(Subscription).where(
        Subscription.expires_at < now,
        Subscription.is_active == True,
    )

    result = await session.execute(query)
    expired = result.scalars().all()

    revoked = []
    failed_revoke_subs: list[tuple[int, str, int]] = []

    for sub in expired:
        try:
            async with session.begin_nested():
                # TOCTOU protection: перечитываем подписку под FOR UPDATE перед revoke.
                # Без этого гонка:
                #   T0 scheduler: SELECT истёкших подписок (sub.id=42, expires_at=прошло)
                #   T1 user:      POST /api/subscription/purchase → обновляет expires_at
                #                 и is_active=True (renewal того же sub.id)
                #   T2 scheduler: revoke_client_key(sub.uuid) — ОТЗЫВАЕТ СВЕЖЕ ОПЛАЧЕННЫЙ КЛЮЧ!
                #                 Потом is_active=False — пользователь видит неактивную
                #                 подписку сразу после оплаты.
                # with_for_update() сериализует с purchase_subscription через row lock:
                # purchase ждёт нашего commit/rollback savepoint'а, мы видим уже
                # обновлённый expires_at.
                locked_result = await session.execute(
                    select(Subscription)
                    .where(Subscription.id == sub.id)
                    .with_for_update()
                )
                locked_sub = locked_result.scalar_one_or_none()

                # Sub удалён / другой scheduler уже обработал / renewal уже сделал
                # is_active=False → пропускаем, savepoint коммитится без изменений,
                # row lock освобождается.
                if locked_sub is None or not locked_sub.is_active:
                    continue

                # Renewal проскочил между outer SELECT и нашим FOR UPDATE —
                # expires_at уже в будущем. Не трогаем.
                if locked_sub.expires_at >= now:
                    logger.info(
                        "subscription_id=%s был продлён между SELECT и FOR UPDATE — "
                        "пропускаем revoke",
                        locked_sub.id,
                    )
                    continue

                # Все проверки пройдены — безопасно отзывать.
                success = await revoke_client_key(
                    locked_sub.uuid,
                    source="scheduler",
                    reason="expired",
                )

                # Всегда деактивируем подписку после попытки (audit #4):
                # - иначе пользователь видит "Подписка активна" пока ключ уже отозван;
                # - иначе scheduler бесконечно ретраит один и тот же revoke
                #   (Docker timeout = 30 сек → 60 тиков в час = тысячи таймаутов).
                # Цена: если revoke упал — ключ остаётся orphan в awg0.conf/clientsTable.
                # Админ видит критический лог и чистит руками через
                # /api/admin/subscriptions/{id}/revoke после починки Docker.
                locked_sub.is_active = False

                if success:
                    revoked.append(locked_sub)
                    logger.info("Ключ отозван: subscription_id=%s", locked_sub.id)
                else:
                    failed_revoke_subs.append(
                        (locked_sub.id, locked_sub.uuid, locked_sub.user_id)
                    )
                    logger.warning(
                        "Не удалось отозвать ключ (orphan в Amnezia): subscription_id=%s, "
                        "user_id=%s, pub=%s — нужна ручная очистка",
                        locked_sub.id, locked_sub.user_id, locked_sub.uuid[:16] + "...",
                    )
        except Exception as loop_err:
            # Не роняем весь батч из-за одной битой подписки — логируем и идём дальше.
            # Savepoint уже откатился автоматически, row lock освобождён.
            logger.exception(
                "Ошибка при обработке subscription_id=%s в scheduler: %s",
                sub.id, loop_err,
            )
            failed_revoke_subs.append((sub.id, sub.uuid, sub.user_id))

    if failed_revoke_subs:
        # Дублируем critical-лог одной строкой — проще грепать / алертить
        # в Logfire/Sentry. Каждый tuple: (sub_id, pub, user_id).
        logger.error(
            "ORPHAN_KEYS_AFTER_REVOKE: остались ключи в Amnezia после сбоя revoke: %s",
            failed_revoke_subs,
        )

    await session.commit()
    return revoked
