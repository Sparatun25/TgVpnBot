#!/bin/bash
set -e

echo "🚀 OnyxVpn Backend Starting..."

# Добавляем appuser в docker группу (если сокет есть).
#
# Базовый образ Debian уже содержит группу docker с дефолтным GID,
# который может не совпадать с GID хоста (например, base=102, host=120).
# Без пересоздания группы appuser добавляется в docker (102), а сокет
# принадлежит группе 120 → permission denied при docker exec.
# Поэтому сначала проверяем совпадение GID и при расхождении пересоздаём группу.
if [ -S /var/run/docker.sock ]; then
  echo "🐳 Настройка доступа к Docker..."
  DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)
  EXISTING_DOCKER_GID=$(getent group docker | cut -d: -f3 || echo "")
  if [ -z "$EXISTING_DOCKER_GID" ]; then
    groupadd -g "$DOCKER_GID" docker
  elif [ "$EXISTING_DOCKER_GID" != "$DOCKER_GID" ]; then
    echo "⚠️  Группа docker имеет GID=$EXISTING_DOCKER_GID, требуется GID=$DOCKER_GID. Пересоздаём..."
    groupdel docker
    groupadd -g "$DOCKER_GID" docker
  fi
  usermod -aG docker appuser
  echo "✅ appuser добавлен в docker группу (GID=$DOCKER_GID)"
fi

# Переключаемся на appuser для запуска приложения
echo "🔐 Переключение на пользователя appuser..."
exec su -s /bin/bash appuser -c "
  # Ожидание PostgreSQL
  echo '⏳ Ожидание PostgreSQL...'
  until pg_isready -h \"\${POSTGRES_HOST:-postgres}\" -p \"\${POSTGRES_PORT:-5432}\" -U \"\${POSTGRES_USER:-postgres}\"; do
    echo 'PostgreSQL недоступен, ожидание...'
    sleep 2
  done

  echo '✅ PostgreSQL готов'

  # Инициализация БД
  echo '🗄️ Инициализация базы данных...'
  python -m database.init_db

  echo '✅ База данных готова'

  # Настройка multiproc-директории для Prometheus.
  # uvicorn --workers 4 создаёт 4 отдельных процесса — каждый пишет свои
  # метрики в .db-файлы здесь, /metrics handler агрегирует через
  # MultiProcessCollector. Бот — отдельный процесс на 9100, ему multiproc
  # не нужен (он один), поэтому PROMETHEUS_MULTIPROC_DIR выставляем только
  # до запуска uvicorn и снимаем перед ботом.
  echo '📊 Настройка Prometheus multiproc...'
  mkdir -p /tmp/prometheus_multiproc
  rm -f /tmp/prometheus_multiproc/*  # чистим stale-файлы от прошлых запусков
  export PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

  # Запуск API и бота в фоне
  echo '🌐 Запуск FastAPI API...'
  uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4 &

  # Снимаем PROMETHEUS_MULTIPROC_DIR, чтобы бот использовал in-memory REGISTRY.
  unset PROMETHEUS_MULTIPROC_DIR

  echo '🤖 Запуск Telegram бота...'
  python -m bot.main &

  # Ожидание всех процессов
  wait
"
