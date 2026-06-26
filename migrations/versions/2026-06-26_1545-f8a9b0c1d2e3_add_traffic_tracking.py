"""add traffic tracking

Revision ID: f8a9b0c1d2e3
Revises: a1b2c3d4e5f6
Create Date: 2026-06-26 15:45:00.000000+00:00

Обёртка для migrations/add_traffic_tracking.sql: ранее эти колонки добавлялись
ручным SQL-скриптом на проде, теперь живут в Alembic-цепочке. Используем
IF NOT EXISTS, чтобы миграция была идемпотентной — повторный запуск на БД,
где SQL уже выполнен, не упадёт.

Используется фоновым сборщиком services/traffic_collector.py, который раз в
TRAFFIC_COLLECT_INTERVAL_SECONDS парсит `wg show awg0 dump` в контейнере
Amnezia и обновляет суммарный трафик + время последнего handshake.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8a9b0c1d2e3'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── Колонки трафика ─────────────────────────────────
    # NOT NULL DEFAULT 0 — для существующих строк берётся 0,
    # для новых INSERT через ORM тоже сработает default=False на стороне Python,
    # но server_default страхует прямые INSERT в обход ORM (например, через psql).
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "total_bytes_received BIGINT NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "total_bytes_sent BIGINT NOT NULL DEFAULT 0"
    )
    # Nullable: NULL = ключ создан, но пользователь ещё ни разу не подключился.
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "last_handshake_at TIMESTAMP WITH TIME ZONE"
    )

    # ─── Комментарии для pg_catalog ──────────────────────
    # COMMENT ON COLUMN IF EXISTS нет в стандартном Postgres, но колонки
    # созданы через IF NOT EXISTS выше — если они уже были, ALTER ничего
    # не сделал, а COMMENT может упасть, что и нужно: зафиксировать описание.
    op.execute(
        "COMMENT ON COLUMN users.total_bytes_received IS "
        "'Суммарный скачанный трафик через WireGuard-туннель, байт. "
        "Обновляется services/traffic_collector.py каждые "
        "TRAFFIC_COLLECT_INTERVAL_SECONDS (по умолчанию 300 сек).'"
    )
    op.execute(
        "COMMENT ON COLUMN users.total_bytes_sent IS "
        "'Суммарный отправленный трафик через WireGuard-туннель, байт. "
        "Обновляется services/traffic_collector.py.'"
    )
    op.execute(
        "COMMENT ON COLUMN users.last_handshake_at IS "
        "'UTC ISO timestamp последнего успешного handshake клиента с сервером "
        "AmneziaWG. NULL = ключ создан, но пользователь ещё ни разу не "
        "подключился. Используется для определения \"онлайн сейчас\" "
        "(handshake < 3 мин назад).'"
    )

    # ─── Индекс "кто онлайн сейчас" ─────────────────────
    # Частичный: WHERE last_handshake_at IS NOT NULL — NULL-значения
    # (никогда не подключался) в индекс не попадают, экономим место.
    # DESC — частый запрос ORDER BY last_handshake_at DESC LIMIT N
    # (active_now в /api/admin/metrics, top-N активных).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_last_handshake_at "
        "ON users (last_handshake_at DESC) WHERE last_handshake_at IS NOT NULL"
    )


def downgrade() -> None:
    # Удаляем индекс и колонки в обратном порядке. IF EXISTS — для
    # повторной откатки на БД, где уже всё снесено.
    op.execute("DROP INDEX IF EXISTS ix_users_last_handshake_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_handshake_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS total_bytes_sent")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS total_bytes_received")
