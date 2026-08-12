# Тестирование

Unit-тесты проекта покрывают логику сервиса без вызова реальных нейросетей.
Все LLM-вызовы заменяются заглушками (`FakeService`, `FakeLLM`), поэтому тесты
быстрые, детерминированные и не зависят от сети.

## Запуск

```bash
# из корня проекта
pytest -q
```

28 тестов, проходят локально и в CI (Debian 13 Trixie, `.github/workflows/ci.yml`).

## Общий подход

- **Герметичность** (`tests/conftest.py`): до импорта приложения задаются dummy-значения
  `APP_ENV` и всех переменных провайдеров — тесты не зависят от реального `.env` и секретов;
- **Без сети**: провайдеры не инициализируют соединений, а LLM-клиент подменяется фейками;
- **Конфиг**: режим окружения фиксирован (`prod`), но тесты читают значения
  (`max_retries` и т.д.) из `app_config`, поэтому корректно работают при любом `APP_ENV`.

## Что проверяется

### HTTP API — `tests/test_api.py`

Эндпоинт `POST /api/generate-look` (через `TestClient`, сервис подменён `FakeService`).

| Кейс | Ожидание |
|---|---|
| Корректный запрос | HTTP `200`, `status: "success"`, заполнены `data.look_variants` и `data.recommendation` |
| Пропущено обязательное поле (`message` / `style` / `gender`) | HTTP `422`, `error_type: "validation"`, поле указано в `details` |
| Недопустимое значение enum (`gender`, `style`) | HTTP `422`, `error_type: "validation"` |
| Возраст вне диапазона 10–100 (`5`, `200`) | HTTP `422`, `error_type: "validation"`, поле `age` |
| `message` короче 5 символов | HTTP `422`, `error_type: "validation"`, поле `message` |
| Исключение в сервисе | HTTP `500`, `error_type: "internal"`, сообщение не пустое |

### Промпты и цепочка провайдеров — `tests/test_llm_client.py`

| Кейс | Что проверяется |
|---|---|
| `build_result_prompt` | Значения `gender` / `age` / `style` / `message` подставлены в шаблон |
| Плейсхолдеры | В результате не осталось `{gender}`, `{age}`, `{style}`, `{user_message}` |
| Структура промпта | Присутствуют ключи `look_variants` и `recommendation` |
| `get_provider_chain` | Порядок провайдеров совпадает с `enabled_providers` из конфига |

### Fallback, ретраи и кэширование — `tests/test_image_maker_service.py`

Проверяются через `ImageMakerService._call_llm` / `generate_look` с фейковым
LLM-клиентом (список провайдеров `yandex`, `gigachat` и управляемое поведение)
и in-memory `FakeCache`. Кэш-ключ строится по фактической модели провайдера
(через `get_model_name()`), поэтому при fallback ключ пересчитывается.

| Кейс | Ожидание |
|---|---|
| Primary недоступен (сетевая ошибка `LLM_CLIENT_REQUEST_FAILED`) | Результат берётся от secondary; primary исчерпывает `max_retries` попыток |
| Сетевая ошибка на первой попытке | Ретрай: ровно 2 вызова, затем успех; secondary не вызывается |
| Ошибка валидации (`LLM_CLIENT_VALIDATION_ERROR`) | Не ретраится (1 вызов), происходит fallback на secondary |
| Все провайдеры недоступны | Поднимается последняя ошибка; каждый провайдер исчерпывает `max_retries` |
| Fallback на secondary | Возвращается `request_hash`, построенный по модели gigachat (отличается от primary) |
| Попадание в кэш secondary | Ответ берётся из кэша, gigachat не вызывается (кэш проверяется до запроса в LLM) |
| Кэш-хит в `generate_look` | Кэш-файл не перезаписывается: `cache.set` не вызывается |
| Битый кэш-файл | Ключ удаляется, запрос проваливается в LLM |
| Fallback через `generate_look` (end-to-end) | `cache.set` пишет данные под хэшем модели gigachat, primary-ключ не создаётся |

### Конфигурация — `tests/test_config.py`

| Кейс | Ожидание |
|---|---|
| `base` | Общие настройки (`wait_time_base: 2`, `temperature: 0.33`, `max_tokens: 2000`, `enabled_providers`) |
| `dev` | Переопределения `max_retries: 2`, `timeout: 45` |
| `prod` | Переопределения `max_retries: 3`, `timeout: 40` |
| Слияние | Режимы наследуют все ключи из `base` |
| Регистрация | `ENV_CONFIGS` указывает на соответствующие конфиги; активный `app_config` согласован |
