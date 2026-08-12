# AI ImageMaker — AI-имиджмейкер

## Краткое описание

**AI ImageMaker** — интеллектуальный сервис подбора стильного образа (лука) на основе характеристик пользователя. По запросу (пол, возраст, стиль, ситуация) генерирует несколько вариантов луков с описанием, целевым назначением и общей рекомендацией.

- Технический стек: Python 3.10+, FastAPI, Pydantic v2, OpenAI-compatible API, tenacity
- AI-провайдеры: Yandex AI Studio (основной) + GigaChat (фолбэк)
- Ключевые возможности: персонализированный подбор, структурированные JSON-ответы, валидация через Pydantic, кэширование, retry-политика, JSON-логирование

## Инструкция по запуску

```bash
python3 -m venv venv

source venv/bin/activate

# Установка проекта с dev-зависимостями (тесты, линтеры, форматтеры)
pip install -e ".[dev]"

# Только runtime-зависимости
pip install .

# Предварительно настроить .env по образцу .env.example
# Dev-сервер (APP_ENV=dev)
uvicorn main:app --reload

# Prod
APP_ENV=prod uvicorn main:app --host 0.0.0.0 --port 8000
```

Документация API: http://127.0.0.1:8000/docs

## Качество кода: линтеры и форматтеры

Инструменты (`black`, `isort`, `flake8`, `mypy`, `pytest`) ставятся вместе с
проектом как dev-зависимости: `pip install -e ".[dev]"`.

Форматирование и проверка стиля:

```bash
# Форматирование и сортировка импортов
black --exclude "venv|\.git|\.mypy_cache|\.pytest_cache|__pycache__" .
isort --skip venv --skip .git --skip .mypy_cache --skip .pytest_cache --skip __pycache__ --profile black .

# Проверка без изменений (для CI/самопроверки)
black --check --exclude "venv|\.git|\.mypy_cache|\.pytest_cache|__pycache__" .
isort --check-only --skip venv --skip .git --skip .mypy_cache --skip .pytest_cache --skip __pycache__ --profile black .
```

Линтеры:

```bash
# Линтер стиля (настройки в .flake8: max-line-length=88, выровнен под black)
flake8 .

# Статическая проверка типов
mypy .
```

Линтеры проверяются одной командой:

```bash
flake8 . && mypy .
```

Тесты (unit, без вызовов реальных нейросетей):

```bash
pytest -q
```

Тесты герметичны: окружение (dummy-ключи провайдеров) задаётся в `tests/conftest.py`,
реальные `.env`/секреты и сетевые вызовы не используются.

## CI (GitHub Actions)

Пайплайн `.github/workflows/ci.yml` запускается на каждый push в `main`/`dev` и
pull request. Job выполняется в контейнере **Debian 13 (Trixie)** и проходит три
шага:

1. **Установка зависимостей** — создание venv и `pip install -e ".[dev]"`;
2. **Линтер** — `flake8`, `mypy`, `black --check`, `isort --check-only`;
3. **Тесты** — `pytest -q`.

## Конфигурация

Режим окружения задаётся переменной `APP_ENV` (`dev` | `prod`, по умолчанию `prod`). Настройки разделены на базовые и переопределения:

- **`.env`** — только credentials и endpoints (ключи Yandex/GigaChat, модель)
- **`config/base.py`** — базовые настройки, общие для всех режимов: `wait_time_base`, `temperature`, `max_tokens`, `enabled_providers`
- **`config/dev.py`** — переопределения для разработки: `max_retries: 2`, `timeout: 45`
- **`config/prod.py`** — переопределения для продакшна (текущие настройки): `max_retries: 3`, `timeout: 40`
  - `enabled_providers: ["yandex", "gigachat"]` — список активных провайдеров. Для временного отключения Yandex оставьте `["gigachat"]`

## Структура проекта

```
main.py                        # FastAPI-приложение, обработчик ошибок валидации
api/routes.py                  # POST /api/generate-look
config/                        # settings.py (APP_ENV) + base.py / dev.py / prod.py
.flake8                        # настройки flake8 (max-line-length=88, выравнено под black)
pyproject.toml                 # зависимости проекта (runtime + dev) и конфигурация pytest
.github/workflows/ci.yml       # GitHub Actions CI (Debian 13 Trixie): deps → lint → tests
tests/                         # unit-тесты: API (200/422), промпты, fallback, ретраи, конфиг
models/schemas.py              # Pydantic-модели запросов/ответов
services/image_maker_service.py # оркестрация: кэш → LLM → валидация
llm/llm_client.py              # клиент LLM (Yandex + GigaChat фолбэк)
llm/system_prompt.py           # шаблон системного промпта
cache/cache_manager.py         # файловый кэш с TTL 10 мин
cache/cleanup.py               # скрипт очистки устаревших кэш-файлов (для cron)
core/log.py                    # JSON-логирование
```

## Описание пайплайна

1. **Запрос** → Pydantic-валидация `LookCreate` (ошибки → 422 `ApiResponseError`)
2. **Хэш-ключ** → `sha256(result_prompt + model_name + temperature)`
3. **Кэш** → при попадании (TTL ≤ 10 мин) мгновенный ответ без вызова LLM
4. **LLM** → сборка `result_prompt` из шаблона + данные пользователя; запрос к Yandex, при ошибке фолбэк на GigaChat
5. **Retry** → tenacity: ретрай только сетевых ошибок (`LLM_CLIENT_REQUEST_FAILED`), экспоненциальный backoff из конфигурации
6. **Валидация ответа** → JSON-парсинг + проверка структуры + строгая проверка `LookData`
7. **Кэширование** → запись результата с timestamp
8. **Ответ** → `ApiResponseSuccess` / `ApiResponseError` (внутренние детали не утекают)

## Очистка кэша

Кэш хранится в `cache/data/` в виде JSON-файлов `{sha256-ключ}.json`. Каждый
файл содержит поле `timestamp` (epoch-время записи). TTL задаётся константой
`CACHE_TTL_SECONDS` в `cache/cache_manager.py` (по умолчанию 10 минут).

Протухшие записи удаляются «лениво» при чтении в `CacheManager.get`, а для
периодической очистки накопленных файлов предназначен скрипт `cache/cleanup.py`:

```bash
# обычный запуск — удаляет файлы старше TTL
python -m cache.cleanup

# пробный запуск без удаления (показывает, что было бы удалено)
python -m cache.cleanup --dry-run

# свои параметры: директория и TTL в секундах
python -m cache.cleanup --cache-dir cache/data --ttl 600
```

Логика скрипта:

1. Обход всех `*.json` файлов в директории кэша.
2. Для каждого файла читается поле `timestamp` из его содержимого.
3. Если возраст `time.time() - timestamp` больше `CACHE_TTL_SECONDS` — файл удаляется.
4. Файлы с отсутствующим/некорректным `timestamp` или повреждённым JSON также
   удаляются — кэш всё равно не может их использовать.

Пример запуска по cron (каждый час):

```cron
0 * * * * cd /путь/к/проекту && venv/bin/python -m cache.cleanup
```

## Модели Pydantic, ответы и DTO

**Запрос** (`LookCreate`):
- `gender` — `male` | `female`
- `age` — 10–100
- `style` — `sporty` | `casual` | `formal` | `informal` | `eccentric`
- `message` — 5–500 символов

**Успешный ответ** (`ApiResponseSuccess` → `data: LookData`):
- `look_variants[]` — 1–5 вариантов: `title`, `target`, `description`
- `recommendation` — общая рекомендация

**Ошибка** (`ApiResponseError`):
- `status`, `error_type` (`validation` | `internal`), `message`, `details[]`

## curl-запросы для проверки

```bash
# Успешная генерация
curl -X POST http://127.0.0.1:8000/api/generate-look \
  -H "Content-Type: application/json" \
  -d '{"gender":"female","age":25,"style":"casual","message":"Свидание в ресторане, хочу выглядеть стильно и элегантно"}'

# Ошибка валидации (422)
curl -X POST http://127.0.0.1:8000/api/generate-look \
  -H "Content-Type: application/json" \
  -d '{"gender":"female","age":25,"style":"casual"}'
```

## Возможные ограничения

- Зависимость от внешних LLM-провайдеров (таймауты, квоты, сетевые ошибки)
- Кэш хранится в файлах (`cache/data/`) с TTL 10 минут — при перезапуске/нескольких инстансах данные могут дублироваться
- Модель может вернуть невалидный JSON или нарушить структуру — обрабатывается как ошибка
- Формат ответа модели завязан на системный промпт; смена модели может потребовать корректировки промпта
