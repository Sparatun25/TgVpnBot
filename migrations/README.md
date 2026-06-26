# Migrations (Alembic)

Все изменения схемы БД — через Alembic. Не используем `Base.metadata.create_all`
и ручные `ALTER TABLE` (те были легаси до P0-рефакторинга).

## Структура

```
alembic.ini                    # конфиг Alembic (ASCII-only из-за cp1251 на Windows)
migrations/
  env.py                       # async env, читает DATABASE_URL из core.config
  script.py.mako               # шаблон новых миграций
  versions/                    # файлы миграций
    <timestamp>-<rev>_<slug>.py
  README.md                    # этот файл
```

## Что внутри

- **Async-first**: `env.py` читает `DATABASE_URL` из `core.config.settings` (pydantic-settings)
  — никакого дублирования URL в env.
- **Двойная совместимость**: работает и на PG (`postgresql+asyncpg://`), и на SQLite
  (`sqlite+aiosqlite:///...`) для тестов и dev. Для этого ENUM определены как
  `VARCHAR + CHECK constraint`, а не нативные PG `CREATE TYPE ... AS ENUM`.
- **`compare_type=True`, `compare_server_default=True`** — autogenerate замечает
  изменения типов колонок и значений defaults.

## Workflow

### 1. Изменил модель → сделал миграцию

```bash
# autogenerate подхватит diff между Base.metadata и текущей БД
DATABASE_URL="sqlite+aiosqlite:///./_gen.db" alembic revision --autogenerate -m "add foo bar"
```

После этого **ОБЯЗАТЕЛЬНО** прочитай сгенерированный файл `migrations/versions/*.py`:
- проверь, что `upgrade()` делает только то, что ты задумал;
- проверь, что `downgrade()` корректно откатывает;
- autogenerate иногда путает переименования колонок с drop+create — поправь руками.

### 2. Накатить на локальную БД

```bash
alembic upgrade head
```

Или через CLI-скрипт:

```bash
python -m database.init_db
```

(он внутри вызывает `alembic upgrade head` через subprocess, чтобы не конфликтовать с event loop приложения).

### 3. Посмотреть текущее состояние

```bash
alembic current       # какая миграция применена
alembic history       # все миграции с их цепочкой
alembic show <rev>    # детали конкретной ревизии
```

### 4. Откатиться

```bash
alembic downgrade -1          # на одну миграцию назад
alembic downgrade base        # полностью откатить всё
alembic downgrade <rev_id>    # до конкретной ревизии
```

### 5. Продакшн: безопасное накатывание

```bash
# Накатить без простоя (использует CREATE INDEX CONCURRENTLY где возможно):
alembic upgrade head

# Посмотреть SQL заранее (для ревью DBA):
alembic upgrade head --sql > migration.sql
```

## Существующая БД (baseline)

Если на проде уже есть БД со старой схемой и хочется начать вести историю
**без пересоздания таблиц**:

```bash
# 1. Пусть Alembic считает текущую БД "применённой до этой ревизии",
#    не выполняя самих миграций:
alembic stamp head

# После этого `alembic current` покажет head, и autogenerate начнёт
# генерировать миграции от текущего состояния.
```

## Правила

1. **Каждое изменение схемы = отдельная миграция.** Не пиши одну миграцию на
   десять PR — нельзя будет откатить только это изменение.
2. **Миграция должна быть обратной.** `downgrade()` обязан корректно откатить
   `upgrade()`. Проверяй локально: `alembic upgrade head && alembic downgrade base`.
3. **Никаких ручных `ALTER TABLE`.** Если нужно поменять колонку — новая миграция,
   даже если «быстрее сделать руками в psql».
4. **Миграции в PR ревью вместе с изменением моделей.** Без `database/models.py`
   миграция бесполезна, и наоборот.
5. **ENUM: VARCHAR + CHECK, не нативный PG type.** Иначе SQLite-тесты сломаются
   (нет поддержки `CREATE TYPE ... AS ENUM`).
6. **Частичные уникальные индексы — через `postgresql_where=` + `sqlite_where=`.**
   Alembic сгенерирует правильный синтаксис для обеих БД.
7. **Никаких заглушек / TODO.** Если не можешь написать downgrade — спроси.

## Troubleshooting

### UnicodeDecodeError: 'charmap' codec

Значит кто-то добавил кириллицу в `alembic.ini`. Этот файл читается Alembic
с OS-locale кодировкой (cp1251 на Windows), поэтому там разрешены только
ASCII-символы. Документация — здесь в README, а не в комментариях `alembic.ini`.

### Не подхватывает новые модели

Убедись, что модель импортируется через `database.models.Base` или напрямую
наследует от него. Alembic сканирует `Base.metadata` — если модель не
зарегистрирована (lazy import, например), autogenerate её не увидит.

### `alembic current` пустое, хотя миграции применялись

Возможно, запускал миграции через `Base.metadata.create_all` (легаси-путь).
Сделай `alembic stamp head`, чтобы Alembic принял текущее состояние за baseline.

### Конфликт при слиянии веток

Если две ветки сделали миграции параллельно:

```bash
alembic merge -m "merge heads" <rev1> <rev2>
```

Это создаст merge-миграцию, которая ничего не делает, но склеит цепочку.
