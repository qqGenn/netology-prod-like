# AI ImageMaker — AI-имиджмейкер

## Краткое описание

**AI ImageMaker** — интеллектуальный сервис подбора стильного образа (лука) на основе характеристик пользователя. По запросу (пол, возраст, стиль, ситуация) генерирует несколько вариантов луков с описанием, целевым назначением и общей рекомендацией.

- Технический стек: Python 3.10+, FastAPI, Pydantic v2, OpenAI-compatible API, tenacity
- AI-провайдеры: Yandex AI Studio (основной) + GigaChat (фолбэк)
- Ключевые возможности: персонализированный подбор, структурированные JSON-ответы, валидация через Pydantic, кэширование, retry-политика, JSON-логирование

## Сценарий использования

Пользователь хочет подобрать образ для конкретной ситуации. Для этого он отправляет запрос с четырьмя параметрами:

1. **Пол** — `male` или `female`;
2. **Возраст** — от 10 до 100 лет;
3. **Предпочитаемый стиль** — `sporty`, `casual`, `formal`, `informal` или `eccentric`;
4. **Ситуация/повод** — текстовое описание (от 5 до 500 символов), например «свидание в ресторане» или «утренняя пробежка в парке».

Сервис на основе этих данных формирует системный промпт для LLM, запрашивает генерацию и возвращает:

- **1–5 вариантов луков**, каждый с названием (`title`), целью (`target`) и подробным описанием (`description`);
- **общую рекомендацию** (`recommendation`) — сводка с советом, как выбрать.

Примеры:

| Пол | Возраст | Стиль | Ситуация |
|---|---|---|---|
| female | 25 | `casual` | «Свидание в ресторане, хочу выглядеть стильно и элегантно» |
| male | 30 | `sporty` | «Утренняя пробежка в парке, хочу выглядеть динамично» |

Повторные запросы с одинаковыми параметрами обслуживаются из кэша без вызова нейросети.

## Архитектура

Проект разделён на слои — каждый отвечает за свою зону ответственности:

| Слой | Модуль | Назначение |
|---|---|---|
| API | `api/routes.py` | HTTP-эндпоинт `POST /api/generate-look`, примеры для OpenAPI, обработчик ошибок валидации |
| Бизнес-логика | `services/image_maker_service.py` | Оркестрация: кэш → LLM → валидация → кэш; ретраи (tenacity) и fallback между провайдерами |
| LLM-модуль | `llm/` | `LLMClient` (OpenAI-совместимый API), реестр провайдеров, шаблон системного промпта, коды ошибок |
| Кэш | `cache/cache_manager.py` | Файловый кэш с TTL (по умолчанию 10 минут) |
| Конфигурация | `config/` | Настройки по режимам окружения (`APP_ENV`: dev/prod) |
| Модели данных | `models/schemas.py` | Pydantic-модели запросов/ответов (DTO) |
| Логирование | `core/log.py` | Структурированное JSON-логирование (консоль + файл) |

### Поток данных

```
Клиент
   │  POST /api/generate-look (JSON)
   ▼
api/routes.py ── Pydantic-валидация LookCreate ── 422 при ошибке
   ▼
services/image_maker_service.generate_look()
   │  1. Формирует хэш-ключ: sha256(result_prompt + model_name + temperature)
   │  2. cache.get(key) ── hit ──► мгновенный ответ из кэша
   │  3. miss: _call_llm()
   │       для каждого провайдера из enabled_providers (yandex → gigachat):
   │         _call_provider() с ретраями tenacity
   │  4. Парсинг и валидация ответа в LookData
   │  5. cache.set(key, data)
   ▼
ApiResponseSuccess / ApiResponseError
```

### Обработка ошибок и fallback

LLM-модуль возвращает ошибки с кодовым префиксом (`llm/errors.py`):

| Код | Значение | Поведение сервиса |
|---|---|---|
| `LLM_CLIENT_REQUEST_FAILED` | Сетевая/временная ошибка | Ретрай (tenacity, `max_retries`), затем фолбэк на следующего провайдера |
| `LLM_CLIENT_JSON_PARSE_ERROR` | LLM вернул невалидный JSON | Без ретрая, пользователю — «ошибка обработки данных» |
| `LLM_CLIENT_VALIDATION_ERROR` | Неверная структура ответа | Без ретрая, пользователю — «ошибка валидации ответа» |

Если primary-провайдер (Yandex) недоступен, сервис автоматически переключается на secondary (GigaChat). Внутренние детали ошибок пользователю не раскрываются — наружу отдаются нейтральные сообщения.

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

Документация API (Swagger UI): http://127.0.0.1:8000/docs

## API: использование

### Эндпоинт

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/generate-look` | Генерация вариантов образов (луков) |

### Параметры запроса (`LookCreate`)

Все поля обязательные:

| Поле | Тип | Ограничения |
|---|---|---|
| `gender` | string (enum) | `male` \| `female` |
| `age` | integer | от 10 до 100 |
| `style` | string (enum) | `sporty` \| `casual` \| `formal` \| `informal` \| `eccentric` |
| `message` | string | от 5 до 500 символов (лишние пробелы по краям удаляются) |

### Примеры запросов

**curl — успешная генерация:**

```bash
curl -X POST http://127.0.0.1:8000/api/generate-look \
  -H "Content-Type: application/json" \
  -d '{"gender":"female","age":25,"style":"casual","message":"Свидание в ресторане, хочу выглядеть стильно и элегантно"}'
```

**curl — ошибка валидации (422, пропущено `message`):**

```bash
curl -X POST http://127.0.0.1:8000/api/generate-look \
  -H "Content-Type: application/json" \
  -d '{"gender":"female","age":25,"style":"casual"}'
```

**Python (requests):**

```python
import requests

resp = requests.post(
    "http://127.0.0.1:8000/api/generate-look",
    json={
        "gender": "female",
        "age": 25,
        "style": "casual",
        "message": "Свидание в ресторане, хочу выглядеть стильно и элегантно",
    },
)
print(resp.status_code, resp.json())
```

### Формат ответа

**Успешный ответ — HTTP 200 (`ApiResponseSuccess` → `data: LookData`):**

```json
{
  "status": "success",
  "data": {
    "look_variants": [
      {
        "title": "Элегантный кэжуал для свидания",
        "target": "Выглядеть уместно и стильно в ресторане",
        "description": "Комбинация тёмных брюк чинос, струящейся блузы и лёгкого жакета. Дополните образ минималистичными украшениями и замшевыми лоферами."
      },
      {
        "title": "Смарт-кэжуал",
        "target": "Сочетать комфорт и элегантность в вечерней обстановке",
        "description": "Классическая рубашка в приглушённых тонах с тёмными джинсами прямого кроя и кроссовками. Акцент — на качественных тканях и чистой гамме."
      }
    ],
    "recommendation": "Отдайте предпочтение приглушённой палитре и чистым силуэтам, чтобы выглядеть уверенно и уместно."
  }
}
```

Ограничения полей ответа:

| Поле | Ограничения |
|---|---|
| `look_variants` | массив из 1–5 элементов |
| `look_variants[].title` | 1–100 символов |
| `look_variants[].target` | 1–300 символов |
| `look_variants[].description` | 10–2000 символов |
| `recommendation` | 10–1000 символов |

**Ошибка валидации — HTTP 422 (`ApiResponseError`):**

```json
{
  "status": "error",
  "error_type": "validation",
  "message": "Ошибка значения 'style': значение 'sorty' недопустимо. Допустимые значения: 'sporty', 'casual', 'formal', 'informal' or 'eccentric'",
  "details": [
    {
      "field": "style",
      "error": "Ошибка значения 'style': значение 'sorty' недопустимо. Допустимые значения: 'sporty', 'casual', 'formal', 'informal' or 'eccentric'"
    }
  ]
}
```

**Внутренняя ошибка — HTTP 500 (`ApiResponseError`):**

```json
{
  "status": "error",
  "error_type": "internal",
  "message": "Внутренняя ошибка сервера. Пожалуйста, попробуйте позже."
}
```

### Коды ответов HTTP

| Код | Когда | Тело |
|---|---|---|
| `200` | Успех, либо «мягкая» ошибка сервиса (LLM недоступен, некорректные данные в кэше и т.п.) | `ApiResponseSuccess` / `ApiResponseError` |
| `422` | Ошибка валидации запроса | `ApiResponseError` (`error_type: validation`) |
| `500` | Необработанное исключение | `ApiResponseError` (`error_type: internal`) |

## Конфигурация

### Режимы окружения (`APP_ENV`)

Переменная `APP_ENV` выбирает набор настроек (`dev` | `prod`, по умолчанию `prod`). Логика в `config/settings.py`:

1. читается `APP_ENV`;
2. берутся базовые настройки из `config/base.py`;
3. поверх накладываются переопределения выбранного режима (`config/dev.py` или `config/prod.py`);
4. итоговый словарь `app_config` доступен по всему проекту (`from config import app_config`).

При неизвестном значении `APP_ENV` приложение не стартует с ошибкой конфигурации.

### Параметры конфигурации (`config/*.py`)

| Параметр | Назначение | dev | prod |
|---|---|---|---|
| `max_retries` | Количество попыток запроса к LLM (tenacity) | 2 | 3 |
| `timeout` | Таймаут запроса к провайдеру, секунды | 45 | 40 |
| `wait_time_base` | Базовый множитель экспоненциального backoff при ретраях | 2 | 2 |
| `temperature` | Температура модели (креативность ответов) | 0.33 | 0.33 |
| `max_tokens` | Максимум токенов в ответе модели | 2000 | 2000 |
| `enabled_providers` | Список активных провайдеров (порядок = приоритет) | `["yandex", "gigachat"]` | `["yandex", "gigachat"]` |

`wait_time_base`, `temperature`, `max_tokens` и `enabled_providers` одинаковы во всех средах и хранятся в `config/base.py`; `max_retries` и `timeout` переопределяются в `dev.py`/`prod.py`.

Для временного отключения Yandex оставьте `enabled_providers: ["gigachat"]` — тогда фолбэк станет единственным провайдером.

### Переменные окружения (`.env`)

`.env` находится вне репозитория (в `.gitignore`), заполняется по образцу `.env.example`. Содержит только credentials и endpoints — параметры поведения приложения хранятся в `config/*.py`.

| Переменная | Назначение | Провайдер |
|---|---|---|
| `APP_ENV` | Режим окружения: `dev` \| `prod` | — |
| `YANDEX_API_KEY` | API-ключ Yandex AI Studio | Yandex |
| `YANDEX_FOLDER_ID` | Идентификатор каталога (folder id) | Yandex |
| `YANDEX_MODEL` | Имя модели (например, `deepseek-v4-flash`) | Yandex |
| `YANDEX_BASE_URL` | Базовый URL OpenAI-совместимого API | Yandex |
| `GIGACHAT_TOKEN` | `base64(client_id:client_secret)` — OAuth-клиентские данные | GigaChat |
| `GIGACHAT_MODEL` | Имя модели (например, `GigaChat-Pro`) | GigaChat |
| `GIGACHAT_BASE_URL` | Базовый URL API | GigaChat |
| `GIGACHAT_OAUTH_URL` | URL OAuth-эндпоинта для получения access-токена | GigaChat |

Если провайдер включён в `enabled_providers`, но хотя бы одна его переменная не заполнена — приложение не стартует с ошибкой конфигурации.

## Кэширование

Файловый кэш (`cache/data/`) хранит результаты генерации по `sha256`-ключу запроса. Ключ учитывает итоговый промпт, модель и температуру, поэтому одинаковый запрос с теми же параметрами обслуживается без обращения к LLM. TTL по умолчанию — 10 минут (`CACHE_TTL_SECONDS` в `cache/cache_manager.py`). Протухшие записи удаляются «лениво» при чтении, для периодической очистки есть скрипт `cache/cleanup.py` (см. раздел «Очистка кэша»).

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

Подробное описание тестов (что и какие кейсы проверяются) — в [TESTING.md](TESTING.md).

## CI (GitHub Actions)

Пайплайн `.github/workflows/ci.yml` запускается на каждый push в `main`/`dev` и
pull request. Job выполняется в контейнере **Debian 13 (Trixie)** и проходит три
шага:

1. **Установка зависимостей** — создание venv и `pip install -e ".[dev]"`;
2. **Линтер** — `flake8`, `mypy`, `black --check`, `isort --check-only`;
3. **Тесты** — `pytest -q`.

## Структура проекта

```
main.py                        # FastAPI-приложение, обработчик ошибок валидации
api/routes.py                  # POST /api/generate-look
config/                        # settings.py (APP_ENV) + base.py / dev.py / prod.py
.flake8                        # настройки flake8 (max-line-length=88, выравнено под black)
pyproject.toml                 # зависимости проекта (runtime + dev) и конфигурация pytest
.github/workflows/ci.yml       # GitHub Actions CI (Debian 13 Trixie): deps → lint → tests
tests/                         # unit-тесты: API (200/422), промпты, fallback, ретраи, конфиг
TESTING.md                     # подробное описание тестов и кейсов
models/schemas.py              # Pydantic-модели запросов/ответов
services/image_maker_service.py # оркестрация: кэш → LLM → валидация
llm/llm_client.py              # клиент LLM (Yandex + GigaChat фолбэк)
llm/providers/                 # реестр провайдеров: yandex.py, gigachat.py
llm/system_prompt.py           # шаблон системного промпта
llm/errors.py                  # коды ошибок LLM-модуля
cache/cache_manager.py         # файловый кэш с TTL 10 мин
cache/cleanup.py               # скрипт очистки устаревших кэш-файлов (для cron)
core/log.py                    # JSON-логирование
```

## Описание пайплайна обработки запроса

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

## Возможные ограничения

- Зависимость от внешних LLM-провайдеров (таймауты, квоты, сетевые ошибки)
- Кэш хранится в файлах (`cache/data/`) с TTL 10 минут — при перезапуске/нескольких инстансах данные могут дублироваться
- Модель может вернуть невалидный JSON или нарушить структуру — обрабатывается как ошибка
- Формат ответа модели завязан на системный промпт; смена модели может потребовать корректировки промпта
