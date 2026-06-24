#!/bin/bash
set -e

echo "🚀 OnyxVpn Backend Starting..."

# Ожидание PostgreSQL
echo "⏳ Ожидание PostgreSQL..."
until pg_isready -h "${POSTGRES_HOST:-postgres}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-postgres}"; do
  echo "PostgreSQL недоступен, ожидание..."
  sleep 2
done

echo "✅ PostgreSQL готов"

# Инициализация БД
echo "🗄️ Инициализация базы данных..."
python -m database.init_db

echo "✅ База данных готова"

# Запуск API и бота в фоне
echo "🌐 Запуск FastAPI API..."
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4 &

echo "🤖 Запуск Telegram бота..."
python -m bot.main &

# Ожидание всех процессов
wait
