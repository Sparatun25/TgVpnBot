# OnyxVpn — CLAUDE.md

## О проекте

**OnyxVpn** — Telegram-бот с Mini App для подключения VPN на движке Amnezia.
Проект = бот (aiogram 3.x) + API/админка (FastAPI) + фронтенд Mini App.

**Главный принцип**: простота для пользователя. Путь от попадания в бот до работающего VPN — минимум шагов, ноль путаницы.

---

## Стек

| Слой | Технология |
|------|-----------|
| Бот | Python 3.12+, aiogram 3.x |
| API / Админка | FastAPI |
| ORM | SQLAlchemy 2.x (async) |
| БД | PostgreSQL |
| Mini App | React + TypeScript, Telegram Web App API |
| Стилизация | CSS Modules или Tailwind (решим по ходу) |
| VPN-движок | Amnezia (ключи через API) |

---

## Архитектура

```
TgVpnBot/
├── bot/            # aiogram бот (handlers, keyboards, middlewares)
├── api/            # FastAPI (REST для Mini App + админка)
├── webapp/         # Mini App фронтенд (React + TS + Vite)
├── core/           # общие модули: БД, конфиг, модели, утилиты
├── services/       # бизнес-логика: Amnezia API, платежи, триалы
├── database/       # SQLAlchemy модели (User, Subscription, Payment)
├── docker/         # nginx.conf для фронтенда
├── docs/           # доки, спеки
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
└── CLAUDE.md       # этот файл
```

### Поток данных

```
Пользователь → Telegram Bot (/start)
  ↓
Telegram Mini App (webapp/)
  ↓ HTTPS → nginx (порт 3000)
  ↓ /api/* → FastAPI backend (порт 8000)
  ↓ PostgreSQL (порт 5432)
  ↓ Amnezia VPN (Docker, сеть amnezia-network)
```

### Компоненты

- **bot/** — aiogram 3.x, команда /start создаёт пользователя в БД и показывает кнопку Mini App
- **api/** — FastAPI, эндпоинты:
  - `GET /api/profile` — профиль пользователя (баланс, подписка, connection_url)
  - `POST /api/subscription/trial` — активация триала (создаёт ключ Amnezia)
  - `POST /api/payment/create` — создание платежа через ЮKassa
  - `POST /api/payment/webhook` — webhook от ЮKassa
  - `GET /admin` — HTML админ-панели с Login Widget
  - `POST /api/admin/login` — авторизация через Login Widget
  - `GET /api/admin/metrics` — метрики для админки
  - `GET /api/admin/subscriptions` — список подписок
- **webapp/** — React + TypeScript + Vite:
  - `src/App.tsx` — главный компонент с табами (VPN, Тарифы, Баланс, Профиль)
  - `src/components/VpnScreen.tsx` — экран VPN с кнопкой активации триала и подключения
  - `src/hooks/useApi.ts` — хук для API запросов с авторизацией через initData
  - `src/hooks/useTelegram.ts` — хук для работы с Telegram WebApp SDK
- **core/** — общие модули:
  - `config.py` — pydantic-settings конфиг (BOT_TOKEN, DATABASE_URL, WEBAPP_URL)
  - `db.py` — async SQLAlchemy сессия
- **database/** — SQLAlchemy модели:
  - `User` — telegram_id, username, balance, referral_code
  - `Subscription` — user_id, uuid, plan_type, expires_at, is_active, **connection_url**
  - `Payment` — user_id, amount, payment_id, status
- **services/** — бизнес-логика:
  - `amnezia.py` — создание/отзыв ключей через Docker exec в контейнер amnezia-awg2
  - `payment_sbp.py` — интеграция с ЮKassa СБП

### AmneziaWG интеграция

**Архитектура:**
- Контейнер `amnezia-awg2` (образ `amnezia-awg2`) работает на том же сервере
- Порт: `45019/udp`
- Подсеть клиентов: `10.8.1.0/24`
- Конфиг сервера: `/opt/amnezia/awg/awg0.conf`
- Список клиентов: `/opt/amnezia/awg/clientsTable` (JSON массив)
- Ключи сервера:
  - `/opt/amnezia/awg/wireguard_server_private_key.key` — приватный ключ сервера
  - `/opt/amnezia/awg/wireguard_server_public_key.key` — публичный ключ сервера
  - `/opt/amnezia/awg/wireguard_psk.key` — preshared key (одинаковый для всех клиентов)

**Структура awg0.conf:**
```ini
[Interface]
PrivateKey = <server_private_key>
Address = 10.8.1.0/24
ListenPort = 45019
# Параметры обфускации AmneziaWG (защита от DPI)
Jc = 5          # Junk packet count (1-128)
Jmin = 10       # Junk packet min size
Jmax = 50       # Junk packet max size
S1 = 120        # Packet size init
S2 = 44         # Packet size response
S3 = 16         # Padding size init
S4 = 12         # Padding size response
H1 = 400426253-669804646   # Hash seeds (4 штуки)
H2 = 887382463-1534683374
H3 = 1625699604-1838847236
H4 = 1879377953-2008054664

[Peer]
PublicKey = <client_public_key>
PresharedKey = <psk_key>
AllowedIPs = 10.8.1.1/32
```

**Структура clientsTable:**
```json
[
  {
    "clientId": "<client_public_key>",
    "userData": {
      "clientName": "OnyxVpn user 123",
      "creationDate": "Wed Jun 25 12:34:56 2026"
    }
  }
]
```

**Процесс создания ключа (services/amnezia.py):**
1. Генерируем пару ключей WireGuard через `wg genkey | wg pubkey` в контейнере
2. Находим свободный IP в подсети `10.8.1.0/24` (парсим `AllowedIPs` из `awg0.conf`)
3. Читаем параметры сервера из `awg0.conf` (Jc, Jmin, Jmax, S1-S4, H1-H4, ListenPort)
4. Читаем `wireguard_psk.key` и `wireguard_server_public_key.key`
5. Добавляем `[Peer]` блок в `awg0.conf`
6. Добавляем запись в `clientsTable` (JSON append)
7. Перезагружаем интерфейс: `awg-quick down /opt/amnezia/awg/awg0.conf && awg-quick up /opt/amnezia/awg/awg0.conf`
8. Собираем vpn:// URL для импорта в AmneziaVPN

**Формат vpn:// ключа:**
```
vpn://base64url(4-byte magic + zlib compressed JSON)
```

Magic bytes: `\x00\x00\x0b\x50`

JSON структура:
```json
{
  "containers": [
    {
      "awg": {
        "H1": "...", "H2": "...", "H3": "...", "H4": "...",
        "Jc": "5", "Jmin": "10", "Jmax": "50",
        "S1": "120", "S2": "44", "S3": "16", "S4": "12",
        "last_config": "<полный конфиг клиента в JSON>",
        "port": "45019",
        "protocol_version": "2",
        "subnet_address": "10.8.1.0",
        "transport_proto": "udp"
      },
      "container": "amnezia-awg2"
    }
  ],
  "defaultContainer": "amnezia-awg2",
  "description": "OnyxVpn",
  "dns1": "1.1.1.1",
  "dns2": "1.0.0.1",
  "hostName": "104.171.128.135"
}
```

`last_config` содержит:
```json
{
  "client_ip": "10.8.1.4",
  "client_priv_key": "<client_private_key>",
  "client_pub_key": "<client_public_key>",
  "server_pub_key": "<server_public_key>",
  "psk_key": "<psk_key>",
  "config": "[Interface]\nAddress = 10.8.1.4/32\n...",
  "hostName": "104.171.128.135",
  "port": 45019,
  "persistent_keep_alive": "25",
  "mtu": "1376",
  "allowed_ips": ["0.0.0.0/0", "::/0"]
}
```

**Отзыв ключа (services/amnezia.py):**
1. Находим `[Peer]` блок по PublicKey (хранится в `Subscription.uuid`)
2. Удаляем блок из `awg0.conf` (regex `\[Peer\].*?PublicKey = <key>.*?(?=\[Peer\]|$)`)
3. Удаляем запись из `clientsTable` по `clientId`
4. Перезагружаем интерфейс: `awg-quick down/up`

**Команды для диагностики:**
```bash
# Посмотреть конфиг сервера
docker exec amnezia-awg2 cat /opt/amnezia/awg/awg0.conf

# Посмотреть список клиентов
docker exec amnezia-awg2 cat /opt/amnezia/awg/clientsTable

# Посмотреть ключи сервера
docker exec amnezia-awg2 cat /opt/amnezia/awg/wireguard_server_private_key.key
docker exec amnezia-awg2 cat /opt/amnezia/awg/wireguard_server_public_key.key
docker exec amnezia-awg2 cat /opt/amnezia/awg/wireguard_psk.key

# Перезагрузить интерфейс вручную
docker exec amnezia-awg2 sh -c "awg-quick down /opt/amnezia/awg/awg0.conf && awg-quick up /opt/amnezia/awg/awg0.conf"

# Сгенерировать ключи вручную
docker exec amnezia-awg2 sh -c "wg genkey"
docker exec amnezia-awg2 sh -c "echo <private_key> | wg pubkey"
```

**Переменные окружения:**
```bash
AMNEZIA_SERVER_HOST=104.171.128.135  # Публичный IP сервера
AMNEZIA_CONTAINER_NAME=amnezia-awg2  # Имя контейнера
```

### Авторизация

**Mini App (в Telegram):**
- Telegram WebApp SDK передаёт `initData` (подписанная строка с user data)
- Фронтенд отправляет `Authorization: Bearer <initData>`
- Бэкенд валидирует через HMAC-SHA256 с ключом `HMAC-SHA256("WebAppData", bot_token)`
- Извлекает `tg_id` из поля `user` в initData

**Админка (в браузере):**
- Telegram Login Widget (отдельный виджет для браузеров)
- Пользователь нажимает кнопку "Войти через Telegram"
- Виджет возвращает `{id, first_name, last_name, username, photo_url, auth_date, hash}`
- Бэкенд валидирует через HMAC-SHA256 с ключом `SHA256(bot_token)` (другой алгоритм!)
- Проверяет `auth_date` (не старше 5 минут)
- Проверяет, что `tg_id` есть в `BOT_ADMIN_IDS`
- Сохраняет `tg_id` в sessionStorage, отправляет в заголовке `X-Admin-Tg-Id`

### Docker-контейнеры

```yaml
postgres:       # PostgreSQL 16, порт 5432
backend:        # FastAPI + aiogram, порт 8000, сеть onyxvpn-network + amnezia-network
frontend:       # nginx со статикой React, порт 3000, сеть onyxvpn-network
amnezia-vpn:    # внешний контейнер (не в docker-compose), сеть amnezia-network
```

### Telegram бот

- **Username:** `@Onyx_vpn24_bot` (хардкодится в `api/admin_ui.py` для Login Widget)
- **Домен Mini App:** `https://onyxvpnbot.ru`
- **Login Widget:** настроен на домен `onyxvpnbot.ru` (должен быть добавлен через @BotFather → My Bots → @Onyx_vpn24_bot → Domain)

### Переменные окружения (.env)

```bash
BOT_TOKEN=...                    # Токен Telegram бота @Onyx_vpn24_bot (обязательный)
BOT_ADMIN_IDS=123,456            # Список ID администраторов через запятую
DATABASE_URL=postgresql+asyncpg://...
WEBAPP_URL=https://onyxvpnbot.ru # URL Mini App (для кнопки в боте)
AMNEZIA_SERVER_HOST=104.171.128.135  # Публичный IP сервера AmneziaWG
AMNEZIA_CONTAINER_NAME=amnezia-awg2  # Имя контейнера AmneziaWG
YUKASSA_SHOP_ID=...
YUKASSA_SECRET_KEY=...
```

### База данных

**Важно:** Alembic не настроен. При изменении моделей нужно вручную выполнять SQL:
```sql
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS connection_url VARCHAR(1024);
```

Или пересоздавать таблицы (потеря данных!):
```bash
docker exec -it onyxvpn-postgres psql -U postgres -d onyxvpn -c "DROP TABLE ..."
```

---

## Дизайн и UX

### Принципы

1. **Простота > всё.** Каждый экран должен быть понятен без инструкций.
2. **Никаких ИИ-штампов.** Запрещены: кремовые фоны (#F4F1EA), кислотные акценты на чёрном, газетные колонки, нумерация 01/02/03 без реальной последовательности.
3. **Котики.** Лого и визуальный стиль — котики. Это наша идентичность.
4. **Telegram-native.** Mini App должен ощущаться как часть Telegram, а не чужеродный сайт. Используем `tg.themeParams`, нативные цвета, MainButton.

### Скилы дизайна (обязательны к применению)

- **frontend-design** — для каждого экрана: сначала план (палитра, типографика, сигнатурный элемент), потом код. Критикуй свой план на шаблонность перед реализацией.
- **taste-skill** — аккуратная визуальная плотность, асимметрия, дорогие палитры. Никаких стандартных ИИ-лейаутов.
- **telegram-mini-app** — TWA API, аутентификация через Telegram, нативные паттерны UX.

### Путь пользователя (user flow)

```
Пользователь заходит в бот
  → /start → приветствие + inline-кнопка «Открыть приложение»
  → Mini App открывается
    → Если новый юзер → экран «Попробовать 3 дня бесплатно»
      → Нажимает → генерируется 3-дневный ключ Amnezia
      → Экран с VPN: кнопка «Скачать Amnezia» + кнопка «Подключить»
    → Если триал заканчивается → уведомление за 24ч и за 1ч
    → Если триал закончился → предложение оплатить
    → Если подписка активна → экран VPN с статусом подключения
    → Баланс → пополнение через СБП
```

### Экраны Mini App

1. **Главный (VPN)** — статус подключения, кнопка «Подключить/Отключить», ссылка на скачивание Amnezia (Play Market / App Store).
2. **Баланс** — текущий баланс, кнопка «Пополнить через СБП», история операций.
3. **Подписка** — тарифы, текущий статус, продление.
4. **Профиль** — имя, ID, дата окончания подписки/триала.

---

## Бизнес-логика

### Триал

- 3 дня бесплатно для каждого нового пользователя.
- Один триал на одного Telegram-юзера (проверка по `telegram_id`).
- Уведомления:
  - За **24 часа** до окончания — красивое сообщение в бот.
  - За **1 час** до окончания — сообщение + предложение оплатить.
- По окончании триала ключ Amnezia деактивируется автоматически.

### Ключи Amnezia

- Генерируются через API (реализуем в `services/amnezia.py`).
- Тип ключа зависит от тарифа: 3 дня (триал), 1 месяц, и т.д.
- Один активный ключ на пользователя.

### Оплата

- СБП для пополнения баланса (интеграция позже, оставим интерфейс в `services/payment.py`).
- Баланс списывается при покупке подписки.

### Админ-панель

- Отдельный раздел в API (`/admin/*`).
- Метрики: количество оформленных ключей, активных пользователей, всего запрошенных ключей.
- CRUD по ключам: продлить, удалить, редактировать.
- Доступ только для администраторов (список ID в конфиге).

---

## Уведомления

- Все уведомления отправляются через бот (aiogram).
- Красивое оформление: эмодзи, структурированный текст, inline-кнопки.
- Таймер уведомлений: Celery или APScheduler (решим при реализации).

---

## Безопасность

- **secure-auth** — валидация `initData` от Telegram в Mini App и API. Никогда не доверяй данным клиента без проверки подписи бота.
- **edge-case-master** — в конце разработки прогони все пограничные случаи.
- API-ключи и секреты — только через env-переменные (pydantic-settings).
- SQL — только через ORM, никаких сырых запросов.

---

## Правила кода

- Python: type hints везде, docstrings для публичных функций.
- Async по умолчанию (aiogram + FastAPI + asyncpg).
- Конфиг через `.env` + pydantic-settings.
- Миграции БД через Alembic.
- Коммиты: conventional commits (`feat:`, `fix:`, `refactor:`).
- Перед коммитом: линтер (ruff), форматтер (ruff format).
- **НИКАКИХ ЗАГЛУШЕК.** Весь код должен быть реальным. Если не можешь написать — спрашивай у пользователя. Никаких `from amnezia_api import add_client` если такого модуля нет. Никаких `# TODO: заменить на реальный код`.

---

## Чеклист перед релизом

- [ ] secure-auth — проверка валидации Telegram initData
- [ ] edge-case-master — все пограничные случаи покрыты
- [ ] Триал: уведомления за 24ч и 1ч работают
- [ ] Один триал на юзера — проверка работает
- [ ] Ключ Amnezia генерируется и деактивируется по сроку
- [ ] Админка: метрики и CRUD ключей
- [ ] Mini App: все экраны, адаптив, Telegram-native
- [ ] Оплата СБП: интерфейс готов (интеграция позже)
