"""Сервис для работы с Amnezia VPN через Docker."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.models import Subscription

logger = logging.getLogger(__name__)

# Таймаут для Docker-команд (секунды)
DOCKER_TIMEOUT = 30


async def _run_docker_command(command: list[str]) -> tuple[int, str, str]:
    """
    Выполнить команду в Docker-контейнере Amnezia.

    Возвращает (return_code, stdout, stderr).
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
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
        logger.error("Таймаут выполнения Docker-команды: %s", " ".join(command))
        return 1, "", "Docker command timeout"

    except Exception as e:
        logger.exception("Ошибка выполнения Docker-команды: %s", e)
        return 1, "", str(e)


async def create_client_key(user_id: int, is_trial: bool) -> str:
    """
    Создать ключ VPN для пользователя в Amnezia.

    Args:
        user_id: ID пользователя в БД.
        is_trial: Если True — создаётся 3-дневный ключ.

    Returns:
        Ссылку формата vless:// или amnezia:// для подключения.

    Raises:
        RuntimeError: Если не удалось создать ключ.
    """
    client_uuid = str(uuid.uuid4())

    # Определяем срок действия ключа
    if is_trial:
        duration_days = settings.trial_days
    else:
        duration_days = 30  # месяц по умолчанию

    # Формируем команду для Docker-контейнера Amnezia
    # В реальности здесь будет конкретная команда Amnezia API
    docker_command = [
        "docker",
        "exec",
        "-i",
        "amnezia-vpn",
        "python3",
        "-c",
        f"""
import json, sys
from amnezia_api import add_client

result = add_client(
    uuid="{client_uuid}",
    duration_days={duration_days},
    user_id={user_id}
)
print(json.dumps(result))
""",
    ]

    return_code, stdout, stderr = await _run_docker_command(docker_command)

    if return_code != 0:
        logger.error(
            "Не удалось создать ключ для user_id=%s: %s",
            user_id,
            stderr,
        )
        raise RuntimeError(f"Amnezia Docker error: {stderr}")

    # Парсим ответ от Amnezia
    try:
        result = json_loads(stdout)
        connection_url = result.get("connection_url", "")

        if not connection_url:
            raise ValueError("Пустая ссылка подключения от Amnezia")

        return connection_url

    except (ValueError, KeyError) as e:
        logger.error("Некорректный ответ от Amnezia: %s", stdout)
        raise RuntimeError(f"Invalid Amnezia response: {e}") from e


async def revoke_client_key(uuid: str) -> bool:
    """
    Удалить ключ пользователя из Amnezia.

    Args:
        uuid: UUID клиента в Amnezia.

    Returns:
        True если ключ успешно удалён.
    """
    docker_command = [
        "docker",
        "exec",
        "-i",
        "amnezia-vpn",
        "python3",
        "-c",
        f"""
from amnezia_api import remove_client
remove_client(uuid="{uuid}")
print("OK")
""",
    ]

    return_code, stdout, stderr = await _run_docker_command(docker_command)

    if return_code != 0:
        logger.error("Не удалось удалить ключ %s: %s", uuid, stderr)
        return False

    return True


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


# Импорт json для парсинга (локально, чтобы не засорять верх файла)
from json import loads as json_loads
