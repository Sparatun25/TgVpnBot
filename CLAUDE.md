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
  - `amnezia.py` — создание/отзыв ключей через Docker exec в контейнер amnezia-vpn
  - `payment_sbp.py` — интеграция с ЮKassa СБП

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

### Переменные окружения (.env)

```bash
BOT_TOKEN=...                    # Токен Telegram бота (обязательный)
BOT_ADMIN_IDS=123,456            # Список ID администраторов через запятую
DATABASE_URL=postgresql+asyncpg://...
WEBAPP_URL=https://onyxvpnbot.ru # URL Mini App (для кнопки в боте)
AMNEZIA_API_URL=http://localhost:8080
AMNEZIA_API_KEY=...
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
