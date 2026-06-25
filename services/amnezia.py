"""Сервис для работы с AmneziaWG через docker exec в контейнер."""

import asyncio
import base64
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.models import Subscription

logger = logging.getLogger(__name__)

# Таймаут для Docker-команд (секунды)
DOCKER_TIMEOUT = 30


# ─────────────────────────────────────────────────────────
# Docker exec helpers
# ─────────────────────────────────────────────────────────

async def _exec_in_container(command: str) -> tuple[int, str, str]:
    """
    Выполнить команду в контейнере AmneziaWG.

    Возвращает (return_code, stdout, stderr).
    """
    docker_cmd = [
        "docker", "exec", "-i",
        settings.amnezia_container_name,
        "sh", "-c", command,
    ]

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

        return process.returncode or 0, stdout, stderr

    except FileNotFoundError:
        logger.error("Docker не найден в системе")
        return 1, "", "Docker executable not found"

    except asyncio.TimeoutError:
        logger.error("Таймаут Docker-команды: %s", command)
        return 1, "", "Docker command timeout"

    except Exception as e:
        logger.exception("Ошибка Docker-команды: %s", e)
        return 1, "", str(e)


async def _read_container_file(path: str) -> str:
    """Прочитать файл из контейнера AmneziaWG."""
    rc, stdout, stderr = await _exec_in_container(f"cat {path}")
    if rc != 0:
        raise RuntimeError(f"Не удалось прочитать {path}: {stderr}")
    return stdout


async def _write_container_file(path: str, content: str) -> None:
    """Записать файл в контейнер AmneziaWG через stdin."""
    docker_cmd = [
        "docker", "exec", "-i",
        settings.amnezia_container_name,
        "sh", "-c", f"cat > {path}",
    ]

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

    if process.returncode != 0:
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Не удалось записать {path}: {stderr}")


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
        "echo \"$PRIVATE $PUBLIC\""
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
        "awg-quick up /opt/amnezia/awg/awg0.conf"
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

    # Строгий формат под парсер мобильных приложений Amnezia
    payload = {
        "containers": [
            {
                "container": "amnezia-awg",
                "hostName": str(settings.amnezia_server_host).strip(),
                "port": str(port),
                "transportProto": "udp",
                "awg": {
                    "clientPrivKey": str(client_priv_key).strip(),
                    "peerPubKey": str(server_pubkey).strip(),
                    "clientIp": f"{client_ip}/32",
                    "allowedIps": "0.0.0.0/0",
                    "dns": "1.1.1.1",
                    "Jc": server_params.get("Jc", "4"),
                    "Jmax": server_params.get("Jmax", "1000"),
                    "Jmin": server_params.get("Jmin", "50"),
                    "S1": server_params.get("S1", "15"),
                    "S2": server_params.get("S2", "23"),
                },
            }
        ],
        "description": "Onyx Premium",
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

async def create_client_key(user_id: int, is_trial: bool) -> tuple[str, str]:
    """
    Создать ключ VPN для пользователя.

    Генерирует пару ключей WireGuard, находит свободный IP,
    добавляет Peer в awg0.conf, перезагружает интерфейс
    и возвращает vpn:// URL для импорта в AmneziaVPN.

    Args:
        user_id: ID пользователя в БД.
        is_trial: Если True — триальный ключ (3 дня).

    Returns:
        Кортеж (vpn_url, client_pub_key).
        vpn_url — URL для подключения через AmneziaVPN.
        client_pub_key — публичный ключ клиента (для хранения в uuid).

    Raises:
        RuntimeError: Если не удалось создать ключ.
    """
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
        return vpn_url, client_pub

    except Exception as e:
        logger.exception("Ошибка создания ключа для user_id=%s: %s", user_id, e)
        raise RuntimeError(f"Не удалось создать VPN-ключ: {e}") from e


async def revoke_client_key(sub_uuid: str) -> bool:
    """
    Удалить ключ пользователя из AmneziaWG.

    Находит Peer по public_key (который хранится в Subscription.uuid),
    удаляет из awg0.conf и clientsTable, перезагружает интерфейс.

    Args:
        sub_uuid: Public key клиента (хранится в Subscription.uuid).

    Returns:
        True если ключ успешно удалён.
    """
    try:
        # 1. Удаляем Peer из конфига
        config = await _read_container_file("/opt/amnezia/awg/awg0.conf")
        new_config = _remove_peer_from_config(config, sub_uuid)

        if new_config == config:
            logger.warning("Ключ %s не найден в awg0.conf", sub_uuid)
            return False

        await _write_container_file("/opt/amnezia/awg/awg0.conf", new_config)

        # 2. Удаляем из clientsTable
        await _update_clients_table(remove_client_id=sub_uuid)

        # 3. Перезагружаем интерфейс
        await _reload_interface()

        logger.info("Ключ %s отозван", sub_uuid)
        return True

    except Exception as e:
        logger.exception("Ошибка отзыва ключа %s: %s", sub_uuid, e)
        return False


async def check_expired_subscriptions(session: AsyncSession) -> list[Subscription]:
    """
    Найти все истёкшие подписки и отозвать ключи.

    Возвращает список обработанных подписок.
    """
    now = datetime.now(timezone.utc)

    query = select(Subscription).where(
        Subscription.expires_at < now,
        Subscription.is_active == True,
    )

    result = await session.execute(query)
    expired = result.scalars().all()

    revoked = []

    for sub in expired:
        success = await revoke_client_key(sub.uuid)

        if success:
            sub.is_active = False
            revoked.append(sub)
            logger.info("Ключ отозван: subscription_id=%s", sub.id)
        else:
            logger.warning(
                "Не удалось отозвать ключ: subscription_id=%s",
                sub.id,
            )

    await session.commit()
    return revoked
