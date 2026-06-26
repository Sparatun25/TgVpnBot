"""Центральный реестр Prometheus-метрик проекта TgVpnBot.

Все метрики определяются на уровне модуля — при первом импорте они
регистрируются в default REGISTRY prometheus_client. Импортируйте
`core.metrics` в любом модуле, где нужно инкрементировать счётчики:

    from core.metrics import trial_activations_total
    trial_activations_total.labels(result="success").inc()

Multiprocess mode (uvicorn --workers 4):
- prometheus_client автоматически читает PROMETHEUS_MULTIPROC_DIR из env
- каждый worker пишет в свою .db-файл в этой директории
- /metrics handler агрегирует через MultiProcessCollector (см. api/main.py)

Cardinality: лейблы должны иметь ОГРАНИЧЕННЫЙ набор значений.
НЕ использовать tg_id/user_id/subscription_id как labels — взорвёт cardinality.
"""

from prometheus_client import Counter, Histogram

# ─────────────────────────────────────────────────────────
# Trial & Subscription
# ─────────────────────────────────────────────────────────

trial_activations_total = Counter(
    "trial_activations_total",
    "Trial activation attempts by result",
    ["result"],  # success, rate_limited, already_used, error
)

subscription_purchases_total = Counter(
    "subscription_purchases_total",
    "Subscription purchases by tariff and action",
    ["tariff_id", "action"],  # tariff_id: monthly/quarter/year; action: new/extended
)

# ─────────────────────────────────────────────────────────
# VPN (AmneziaWG)
# ─────────────────────────────────────────────────────────

vpn_keys_created_total = Counter(
    "vpn_keys_created_total",
    "VPN keys created via services/amnezia.py:create_client_key",
    ["is_trial", "plan_type"],  # is_trial: "true"/"false"; plan_type: trial/monthly/quarter/year/unknown
)

vpn_keys_revoked_total = Counter(
    "vpn_keys_revoked_total",
    "VPN keys revoked (success/noop/failure) with source and reason",
    [
        "result",  # success, noop, failure
        "source",  # api, scheduler
        "reason",  # expired, manual, desync
    ],
)

docker_exec_duration_seconds = Histogram(
    "docker_exec_duration_seconds",
    "Docker exec command duration in services/amnezia.py:_exec_in_container",
    ["command_kind"],  # keygen, read, write, reload
    # Подобраны под типичные операции AmneziaWG:
    # keygen: wg genkey | wg pubkey (10-50ms)
    # read: cat awg0.conf, cat clientsTable (5-20ms)
    # write: редактирование conf и clientsTable (10-50ms)
    # reload: awg-quick down/up (100-500ms)
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

docker_exec_errors_total = Counter(
    "docker_exec_errors_total",
    "Docker exec errors by kind",
    ["error_kind"],  # timeout, not_found, runtime, unknown
)

# ─────────────────────────────────────────────────────────
# Payments (ЮKassa СБП)
# ─────────────────────────────────────────────────────────

payments_created_total = Counter(
    "payments_created_total",
    "Payment creation attempts by kind and resulting status",
    [
        "kind",    # stub, real
        "status",  # pending, waiting_for_capture, error
    ],
)

payments_succeeded_total = Counter(
    "payments_succeeded_total",
    "Payments that completed successfully (source of truth for revenue events)",
    ["kind"],  # stub, real, sbp
)

# Без лейблов: это глобальный счётчик revenue. Копейки → integer.
# В Grafana конвертировать в рубли: rate(payments_amount_total_kopecks[5m]) / 100.
payments_amount_total_kopecks = Counter(
    "payments_amount_total_kopecks",
    "Total payment amount in kopecks (sum across all kinds and statuses)",
)

payment_webhook_rejected_total = Counter(
    "payment_webhook_rejected_total",
    "Webhook events rejected for invalid data",
    ["reason"],  # unknown_status, unknown_payment_id, ip_forbidden
)

# ─────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────

db_slow_queries_total = Counter(
    "db_slow_queries_total",
    "SQL queries that exceeded SLOW_QUERY_THRESHOLD_MS (see core/db.py)",
)

# ─────────────────────────────────────────────────────────
# Bot notifications
# ─────────────────────────────────────────────────────────

notifications_sent_total = Counter(
    "notifications_sent_total",
    "Bot notifications sent to users, by type",
    [
        "type",  # trial_24h, trial_1h, expired, inactive_15m, inactive_3h, inactive_24h
    ],
)
