-- Миграция: добавление полей для отслеживания неактивных ключей
-- Дата: 2026-06-25

-- Добавляем поля для отслеживания активности ключей
ALTER TABLE users ADD COLUMN IF NOT EXISTS key_created_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS notified_inactive_15m BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS notified_inactive_3h BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS notified_inactive_24h BOOLEAN DEFAULT FALSE;

-- Комментарии для документации
COMMENT ON COLUMN users.key_created_at IS 'Время создания VPN ключа (для отслеживания неактивных)';
COMMENT ON COLUMN users.last_activity_at IS 'Время последней активности пользователя';
COMMENT ON COLUMN users.notified_inactive_15m IS 'Отправлено уведомление через 15 минут после создания ключа';
COMMENT ON COLUMN users.notified_inactive_3h IS 'Отправлено уведомление через 3 часа после создания ключа';
COMMENT ON COLUMN users.notified_inactive_24h IS 'Отправлено уведомление через 24 часа после создания ключа';
