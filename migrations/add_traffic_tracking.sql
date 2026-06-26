-- Миграция: добавление полей для трекинга трафика WireGuard
-- Дата: 2026-06-26
-- Применяется: psql -f migrations/add_traffic_tracking.sql
--
-- Используется фоновым сборщиком services/traffic_collector.py,
-- который раз в N секунд парсит `wg show awg0 dump` в контейнере Amnezia
-- и обновляет суммарный трафик + время последнего handshake.

ALTER TABLE users ADD COLUMN IF NOT EXISTS total_bytes_received BIGINT NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS total_bytes_sent BIGINT NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_handshake_at TIMESTAMP WITH TIME ZONE;

-- Комментарии для документации в pg_catalog
COMMENT ON COLUMN users.total_bytes_received IS 'Суммарный скачанный трафик через WireGuard-туннель, байт. Обновляется services/traffic_collector.py каждые TRAFFIC_COLLECT_INTERVAL_SECONDS (по умолчанию 300 сек).';
COMMENT ON COLUMN users.total_bytes_sent IS 'Суммарный отправленный трафик через WireGuard-туннель, байт. Обновляется services/traffic_collector.py.';
COMMENT ON COLUMN users.last_handshake_at IS 'UTC ISO timestamp последнего успешного handshake клиента с сервером AmneziaWG. NULL = ключ создан, но пользователь ещё ни разу не подключился. Используется для определения "онлайн сейчас" (handshake < 3 мин назад).';

-- Индекс для быстрой выборки "кто онлайн сейчас" (active_now в /api/admin/metrics).
-- WHERE last_handshake_at IS NOT NULL — частичный индекс, потому что NULL
-- означает "никогда не подключался" и нас не интересует.
CREATE INDEX IF NOT EXISTS ix_users_last_handshake_at
    ON users (last_handshake_at DESC)
    WHERE last_handshake_at IS NOT NULL;
