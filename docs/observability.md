# Observability — структурированные логи и метрики

Документ для разработчиков и DevOps. Описывает как читать логи, где смотреть метрики, какие env vars крутить и как дебажить типовые проблемы.

---

## Архитектура в двух словах

В рантайме у нас **5 процессов** с разными регистрами метрик:

```
┌─────────────────────────────────────────────────────────────────┐
│ onyxvpn-backend контейнер                                       │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────┐ │
│  │ uvicorn      │  │ uvicorn      │  │ uvicorn      │  │ ... │ │  4 worker'а
│  │ worker #1    │  │ worker #2    │  │ worker #3    │  │ #4  │ │  (FastAPI)
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──┬──┘ │
│         └──────────────────┴──────────────────┴─────────────┘   │
│                              ▼                                  │
│            /metrics handler + MultiProcessCollector             │
│                         (порт 8000)                             │
│                                                                 │
│  ┌────────────────────────────────────────────┐                 │
│  │ bot.main (отдельный процесс, in-memory)    │                 │
│  │   start_http_server(9100) → :9100/metrics  │                 │
│  └────────────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────┘

Shared: /tmp/prometheus_multiproc/*.db — uvicorn workers пишут сюда.
Bot НЕ использует этот каталог (один процесс → in-memory REGISTRY).
```

---

## Логирование

### Формат

| `LOG_FORMAT` | Когда использовать | Вид |
|---|---|---|
| `console` (default) | Локальная разработка, `docker logs` глазами | Цветные строки с timestamp, level, logger, message |
| `json` | Прод: log aggregator (Loki, ELK, Datadog) | Одна строка JSON на лог, легко парсить |

Поведение по умолчанию (`LOG_FORMAT=console`, `LOG_LEVEL=INFO`) визуально близко к прежнему `basicConfig`. Если ничего не настраивать — всё работает как раньше, но теперь с request_id в каждой строке.

### Request-ID корреляция

Каждый HTTP-запрос получает `request_id`:
- Берётся из заголовка `X-Request-ID`, если клиент прислал.
- Иначе генерируется `uuid4().hex`.
- Кладётся в `request.state.request_id`, в ContextVar и в response header `X-Request-ID`.
- Через `structlog.contextvars.merge_contextvars` автоматически добавляется в **каждый** лог этого запроса — DB, Amnezia, payments, всё.

Для Telegram-бота: `update_id` используется как `request_id` (`upd-123456789`), плюс `tg_id` и `chat_id`. Это работает через `bind_request_id_for_update` в `UpdateContextMiddleware` (`bot/main.py`).

**Пример console-вывода:**
```
2026-06-26T14:23:18Z [info] api.routes activate_trial user_id=42 result=success request_id=a1b2c3d4e5f67890
2026-06-26T14:23:18Z [info] services.amnezia create_client_key user_id=42 ip=10.8.1.4 request_id=a1b2c3d4e5f67890
2026-06-26T14:23:18Z [info] services.amnezia keygen_docker_exec duration_ms=42 command_kind=keygen request_id=a1b2c3d4e5f67890
```

**Пример JSON-вывода (одна запись):**
```json
{"event":"activate_trial","timestamp":"2026-06-26T14:23:18.412Z","level":"info","logger":"api.routes","user_id":42,"result":"success","request_id":"a1b2c3d4e5f67890"}
```

### Env vars

| Var | Default | Описание |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FORMAT` | `console` | `console` (цвет) или `json` (агрегатор) |

---

## Метрики

### Endpoints

| Endpoint | Процесс | Multiprocess | Файл/код агрегации |
|---|---|---|---|
| `GET /metrics` (порт 8000) | uvicorn | Да, через `MultiProcessCollector` | `api/main.py:169` |
| `GET /metrics` (порт 9100) | bot | Нет, in-memory | `bot/main.py:57` |

Оба endpoint'а **НЕ аутентифицированы** — закрываются на уровне сети (internal Docker network / nginx IP-allowlist). В `docker-compose.yml` НЕ маппим `9100` наружу.

### HTTP-метрики (auto, через Instrumentator)

```
http_requests_total{method, handler, status}        # счётчик запросов
http_request_duration_seconds_bucket{...}           # гистограмма латентности
http_requests_in_progress{handler}                  # gauge активных запросов
```

`/health`, `/ready`, `/metrics`, `/docs`, `/redoc`, `/openapi.json` исключены из instrumentator — нечего мониторить.

### Бизнес-метрики (custom, 12 штук)

Все определены в `core/metrics.py`. Кардинальность лейблов строго ограничена — **НЕЛЬЗЯ** использовать `tg_id`, `user_id`, `subscription_id` как labels.

#### Trial & Subscription

| Метрика | Labels | Где инкрементируется |
|---|---|---|
| `trial_activations_total` | `result` ∈ {success, rate_limited, already_used, error} | `api/routes.py:activate_trial` |
| `subscription_purchases_total` | `tariff_id`, `action` ∈ {new, extended} | `api/routes.py:purchase_subscription` |

#### VPN (AmneziaWG)

| Метрика | Labels | Где |
|---|---|---|
| `vpn_keys_created_total` | `is_trial` ("true"/"false"), `plan_type` (trial/monthly/quarter/year/unknown) | `services/amnezia.py:create_client_key` |
| `vpn_keys_revoked_total` | `result` (success/noop/failure), `source` (api/scheduler), `reason` (expired/manual/desync) | `services/amnezia.py:revoke_client_key` |
| `docker_exec_duration_seconds` | `command_kind` (keygen/read/write/reload) — Histogram | `services/amnezia.py:_exec_in_container` |
| `docker_exec_errors_total` | `error_kind` (timeout/not_found/runtime/unknown) | `services/amnezia.py:_exec_in_container` |

#### Payments (ЮKassa СБП)

| Метрика | Labels | Где |
|---|---|---|
| `payments_created_total` | `kind` (stub/real), `status` (pending/waiting_for_capture/error) | `services/payment_sbp.py:create_sbp_payment` + `api/routes.py:create_payment` (STUB) |
| `payments_succeeded_total` | `kind` (stub/real/sbp) | `api/routes.py:payment_webhook` (SUCCEEDED branch) |
| `payments_amount_total_kopecks` | — (unlabeled Counter) | `api/routes.py:payment_webhook` — **source of truth для revenue** |
| `payment_webhook_rejected_total` | `reason` (unknown_status/unknown_payment_id/ip_forbidden) | `api/routes.py:payment_webhook` |

#### Database

| Метрика | Labels | Где |
|---|---|---|
| `db_slow_queries_total` | — | `core/db.py:after_cursor_execute` (запросы > 500ms) |

#### Bot notifications

| Метрика | Labels | Где |
|---|---|---|
| `notifications_sent_total` | `type` ∈ {trial_24h, trial_1h, expired, inactive_15m, inactive_3h, inactive_24h} | `bot/services/scheduler.py` |

### PromQL-примеры

```promql
# Trial conversion rate
sum(rate(trial_activations_total{result="success"}[1h]))
  / sum(rate(trial_activations_total[1h]))

# Revenue за последние 24 часа (в рублях)
sum(increase(payments_amount_total_kopecks[24h])) / 100

# 95-й перцентиль латентности profile endpoint
histogram_quantile(0.95,
  sum by (le) (rate(http_request_duration_seconds_bucket{handler="/api/profile"}[5m])))

# Активные ключи (rate-of-change)
sum(rate(vpn_keys_created_total[5m])) - sum(rate(vpn_keys_revoked_total{result="success"}[5m]))

# Топ медленных эндпоинтов
topk(5, sum by (handler) (rate(http_request_duration_seconds_sum[5m])))

# Доля отклонённых webhook'ов
sum(rate(payment_webhook_rejected_total[5m]))
  / (sum(rate(payments_succeeded_total[5m])) + sum(rate(payment_webhook_rejected_total[5m])))
```

---

## Health probes

| Endpoint | Назначение | Проверяет |
|---|---|---|
| `GET /health` | Liveness — процесс жив | Только HTTP 200 |
| `GET /ready` | Readiness — готов принимать трафик | `SELECT 1` к БД; 503 если БД недоступна |

- Docker healthcheck: `curl -fsS http://localhost:8000/health`
- Kubernetes livenessProbe: `/health`
- Kubernetes readinessProbe: `/ready` — балансировщик уберёт pod из rotation пока БД недоступна

---

## Multiprocess mode

**Проблема:** uvicorn `--workers 4` запускает 4 отдельных процесса. У каждого свой регистр метрик в памяти. Prometheus будет видеть только тот worker, к которому обратился — счётчики дрейфуют.

**Решение:** `PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc`.

- Каждый worker пишет свои Counter/Histogram в `.db`-файлы в этой директории.
- `/metrics` handler создаёт чистый `CollectorRegistry()`, натравливает на него `MultiProcessCollector(registry)` — он агрегирует значения со всех `.db`-файлов.
- `prometheus_client` сам читает `PROMETHEUS_MULTIPROC_DIR` из env при создании Counter/Histogram.

**Где настраивается:**
- `core/config.py:81` — `prometheus_multiproc_dir` (default `/tmp/prometheus_multiproc`).
- `docker-entrypoint.sh:42-44` — `mkdir + rm -f` и `export` ПЕРЕД запуском uvicorn.
- `docker-entrypoint.sh:51` — `unset` ПЕРЕД запуском бота, чтобы бот использовал in-memory REGISTRY (один процесс).

**Stale files:** при `kill -9` worker'а `.db`-файлы остаются. `rm -f /tmp/prometheus_multiproc/*` в entrypoint чистит их при старте.

**Бот** на `:9100` НЕ использует multiproc — `start_http_server()` поднимает HTTP-сервер с default `REGISTRY` (in-memory). PROMETHEUS_MULTIPROC_DIR для бота явно снимается в entrypoint, иначе Counter'ы бота писали бы в `.db` файлы uvicorn'а.

### Prometheus scrape config

```yaml
scrape_configs:
  - job_name: onyxvpn-api
    static_configs:
      - targets: ['onyxvpn-backend:8000']
    metrics_path: /metrics

  - job_name: onyxvpn-bot
    static_configs:
      - targets: ['onyxvpn-backend:9100']
    metrics_path: /metrics
```

Prometheus ходит через Docker network (internal `onyxvpn-network`). Порты НЕ публикуются наружу через `docker-compose.yml`.

---

## Локальная разработка

### Быстрая проверка

```bash
# 1. Запустить backend
python -m api.main

# 2. В другом терминале — health
curl -i http://localhost:8000/health   # → 200 {"status":"ok"}
curl -i http://localhost:8000/ready    # → 200 {"status":"ready","db":"ok"}

# 3. Метрики (uvicorn в dev — 1 worker, single-process mode)
curl -s http://localhost:8000/metrics | head -20

# 4. JSON-логи
LOG_FORMAT=json python -m api.main 2>&1 | head -5
```

### Тест с X-Request-ID

```bash
curl -H "X-Request-ID: my-trace-123" http://localhost:8000/api/profile
# В логах все записи этого запроса содержат request_id="my-trace-123"
```

### Метрики после бизнес-события

```bash
# Активируем триал
curl -X POST -H "Authorization: Bearer <initData>" http://localhost:8000/api/subscription/trial

# Проверяем счётчик
curl -s http://localhost:8000/metrics | grep trial_activations_total
# Ожидание: trial_activations_total{result="success"} 1.0
```

> ⚠️ **Labeled Counter'ы появляются в `/metrics` только после первого `.inc()`** с соответствующими label values. Это нормальное поведение prometheus_client, не баг. Чтобы увидеть все возможные label combinations в Grafana — нужно либо сначала потрогать каждую ветку, либо настроить `metric_relabel_configs` в Prometheus.

### Валидация формата

```bash
pip install promtool
promtool check metrics <(curl -s http://localhost:8000/metrics)
# Ожидание: no errors
```

---

## Troubleshooting

### `/metrics` показывает только `python_gc_*` (нет наших метрик)

`PROMETHEUS_MULTIPROC_DIR` установлен, но в `CollectorRegistry()` ничего не попало. Проверьте:

```bash
# Внутри контейнера:
ls /tmp/prometheus_multiproc/
# Должны быть .db файлы (по одному на worker)

# Если пусто — модули с метриками не импортированы в этом worker.
# Убедитесь, что `from core import metrics` есть в api/main.py.
```

### Counter'ы прыгают между значениями при скрейпе

Классический симптом: один worker ответил, увидели 42, следующий скрейп — увидели 17. Это значит `MultiProcessCollector` не подключён:

```python
# api/main.py — должно быть:
if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    data = generate_latest(registry)
```

### В логах нет request_id

`RequestIdMiddleware` не зарегистрирован или зарегистрирован ПОСЛЕ другого middleware. Должен быть **первым**:

```python
# api/main.py
app.add_middleware(RequestIdMiddleware)  # ПЕРВЫМ
app.add_middleware(CORSMiddleware, ...)
app.add_middleware(SecurityHeadersMiddleware)
```

### В логах бота нет request_id

`UpdateContextMiddleware` не зарегистрирован. Должен быть на `dp.update.middleware()` (ловит ВСЕ типы update'ов: message, callback_query, inline_query):

```python
# bot/main.py
dp.update.middleware(UpdateContextMiddleware())  # ДО include_router
```

### Бот не отдаёт метрики на 9100

```bash
# Проверьте что PROMETHEUS_MULTIPROC_DIR НЕ унаследован ботом:
docker exec onyxvpn-backend sh -c 'ps -ef | grep bot.main'

# В entrypoint должно быть `unset PROMETHEUS_MULTIPROC_DIR` между uvicorn и ботом.
# Иначе Counter'ы бота будут писать в .db файлы вместо in-memory REGISTRY
# и 9100/metrics отдаст пустой ответ.
```

### `db_slow_queries_total` всегда 0

Либо порог не превышается (slow-query начинается с 500ms), либо событие `after_cursor_execute` не вызывается. Проверьте:

```python
# core/db.py — должно быть:
from core.metrics import db_slow_queries_total
...
db_slow_queries_total.inc()
```

### Stale `.db` файлы

Если контейнер был убит `kill -9`, файлы в `/tmp/prometheus_multiproc/` могли остаться. `rm -f` в entrypoint чистит их при старте — но если контейнер запускали НЕ через entrypoint, почистите вручную:

```bash
docker exec onyxvpn-backend rm -f /tmp/prometheus_multiproc/*
docker restart onyxvpn-backend
```

---

## Файлы и зависимости

### Новые / изменённые

- `core/logging.py` — `setup_logging()`, `get_logger()`
- `core/metrics.py` — все 12 Counter/Histogram
- `core/middleware.py` — `RequestIdMiddleware`, `bind_request_id_for_update`, `request_id_var`
- `core/config.py` — `log_level`, `log_format`, `metrics_bot_port`, `prometheus_multiproc_dir`
- `core/db.py` — `db_slow_queries_total.inc()` в slow-query handler
- `api/main.py` — `setup_logging()`, `RequestIdMiddleware`, `/ready`, `/metrics` с `MultiProcessCollector`, Instrumentator
- `bot/main.py` — `setup_logging()`, `start_http_server(9100)`, `UpdateContextMiddleware`
- `bot/services/scheduler.py` — `notifications_sent_total` в 5 функциях
- `services/amnezia.py` — `vpn_keys_created_total`, `vpn_keys_revoked_total`, `docker_exec_duration_seconds`, `docker_exec_errors_total`
- `services/payment_sbp.py` — `payments_created_total`
- `api/routes.py` — trial/subscription/payments метрики
- `docker-entrypoint.sh` — `mkdir + rm + export` multiproc dir перед uvicorn, `unset` перед ботом
- `Dockerfile.backend` — `EXPOSE 8000 9100`

### requirements.txt

```
structlog==26.1.0
prometheus-client==0.25.0
prometheus-fastapi-instrumentator==8.0.2
```

---

## Что **не** покрыто (out of scope)

- **OpenTelemetry tracing** — пока YAGNI. Если понадобится — `opentelemetry-instrumentation-fastapi` + `opentelemetry-instrumentation-sqlalchemy`, всё через OTLP exporter.
- **Gauge-метрики** — активные подписки считаются в PromQL: `rate(created) - rate(revoked)`. Если нужен абсолютный gauge (например, "сколько user'ов в БД") — это задача отдельного cron + Gauge.
- **Аутентификация `/metrics`** — на уровне сети. Если выставлять наружу — добавить bearer-токен или basic-auth.
- **Alertmanager** — когда появится Prometheus, нужны алерты на `rate(payment_webhook_rejected_total[5m]) > 0`, `histogram_quantile(0.95, ...)` latency budget, `db_slow_queries_total` rate. Отдельная задача.
