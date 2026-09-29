# Document Workflow Monolith

## Описание проекта

Это **намеренно неидеальное** монолитное приложение на Django для системы внутреннего документооборота. Проект создан для учебных целей — демонстрирует антипаттерны, уязвимости и архитектурные проблемы, которые нужно исправить в процессе рефакторинга.

## Бизнес-контекст

Система для управления документами (договоры, служебные записки, счета) с процессом согласования:
- **< 1000 ₽** → только руководитель отдела
- **1000–10000 ₽** → руководитель + юрист
- **> 10000 ₽** → руководитель + юрист + финансовый директор

Документ можно отклонить на любом этапе с комментарием. После согласования документ регистрируется в архиве. Ведётся полная история действий.

## Технологический стек

- Python 3.10+ (проверено на 3.13)
- Django 4.2, Django REST Framework, drf-spectacular (Swagger на `/api/docs/`)
- djangorestframework-simplejwt (JWT)
- PostgreSQL 15 (psycopg 3); для запуска без Postgres — `USE_SQLITE=1`
- Redis (сконфигурирован как cache backend, но приложением не используется)

## Намеренные архитектурные проблемы

Все проблемные места помечены в коде комментариями `# УЯЗВИМОСТЬ:` и `# АНТИПАТТЕРН:`.
Поиск по этим словам даёт полный список точек рефакторинга.

### ⚠️ Уязвимости безопасности:
1. **SQL-инъекции** — `services.search_documents_raw` (конкатенация `search`), `services.archive_list_raw` (`ORDER BY` без whitelist), `views.DocumentViewSet.approvals` (SQL прямо во view)
2. **MD5 без соли** — `utils.hash_password`, `PASSWORD_HASHERS` в settings начинается с `UnsaltedMD5PasswordHasher`
3. **Секреты в коде** — `SECRET_KEY`, пароль БД в `config/settings.py`; `DEBUG=True`, `ALLOWED_HOSTS=['*']`
4. **Хардкод ролей** — `if user.role == 'manager'` в views, services и utils (три копии)
5. **Валидация** — `AUTH_PASSWORD_VALIDATORS=[]`; роль при регистрации задаёт клиент; `status` документа writable через PUT; отрицательные суммы допустимы
6. **IDOR** — detail-эндпоинты (`GET/PUT/DELETE /documents/{id}/`, `history`, `approvals`) не проверяют владельца

### 🏗️ Архитектурные проблемы:
7. **God Class** — `DocumentService` регистрирует пользователей, создаёт/правит/удаляет документы, согласует, архивирует, пишет историю и выполняет SQL
8. Бизнес-логика и SQL во views (нарушение слоистости)
9. Нет абстракций (репозиториев, интерфейсов), глобальный синглтон `service` без DI
10. Нет транзакций: документ / approval / history сохраняются отдельными запросами
11. Все домены в одном приложении `apps/documents`
12. Одна миграция `0001_initial.py` на все таблицы
13. Redis подключён, но не используется
14. Логирование через `print()`; `LOGGING` фактически отключён
15. Нет FSM: статус можно выставить напрямую, магические числа `1000` / `10000` внутри `approve_document`, деньги через `float`
16. `utils.py` — свалка: криптография, генерация номеров, роли и «логгер» в одном файле

### 📦 Bounded Contexts (перемешаны):
- User Management (пользователи, роли)
- Document Lifecycle (создание, редактирование документов)
- Approval Workflow (процесс согласования)
- Audit & History (история действий)
- Archive (архивация)

## Установка и запуск

### Вариант A: локально

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/Mac
pip install -r requirements.txt
```

Нужен PostgreSQL на `localhost:5432` с базой/пользователем из `config/settings.py`:

```sql
CREATE ROLE document_user LOGIN PASSWORD 'document_password';
CREATE DATABASE document_workflow OWNER document_user;
```

Либо без Postgres — SQLite (на Windows PowerShell: `$env:USE_SQLITE=1`):

```bash
USE_SQLITE=1 python manage.py migrate
```

Дальше:

```bash
python manage.py migrate
python manage.py loaddata fixtures/demo.json   # демо-пользователи + 1 документ
python manage.py runserver
```

### Вариант B: docker-compose

```bash
docker compose up --build
```

Поднимает web + postgres:15 + redis:7, применяет миграции и загружает фикстуру.

### Демо-пользователи (пароль у всех `pass`, хеш — unsalted MD5)

| username   | role     | department      |
|------------|----------|-----------------|
| `employee` | employee | Закупки         |
| `manager`  | manager  | Закупки         |
| `lawyer`   | lawyer   | Правовой отдел  |
| `cfo`      | cfo      | Финансовый отдел|

Swagger: http://localhost:8000/api/docs/ · схема: `/api/schema/` · Redoc: `/api/redoc/`

### Быстрый сценарий через curl

```bash
# токен
curl -s -X POST localhost:8000/api/token/ -H "Content-Type: application/json" \
     -d '{"username":"employee","password":"pass"}'
# отправить демо-документ на согласование
curl -s -X POST localhost:8000/api/documents/1/submit/ -H "Authorization: Bearer <access>"
# SQL-инъекция (увидеть чужие документы)
curl -s -G localhost:8000/api/documents/search-raw/ --data-urlencode "search=%' OR 1=1 --" \
     -H "Authorization: Bearer <access>"
```

## Структура проекта

```
document-workflow-monolith/
├── config/
│   ├── settings.py        # ⚠️ SECRET_KEY, пароль БД, DEBUG=True, MD5-хешер
│   └── urls.py            # admin, JWT, swagger, include(apps.documents.urls)
├── apps/documents/        # ⚠️ ВСЕ 5 доменных зон в одном приложении
│   ├── models.py          # User, Document, Approval, History, ArchiveRecord
│   ├── views.py           # ⚠️ fat controllers, IDOR, SQL во view, print()
│   ├── services.py        # ⚠️ DocumentService — God Class + raw SQL с конкатенацией
│   ├── serializers.py     # ⚠️ поверхностная валидация, writable role/status
│   ├── utils.py           # ⚠️ MD5, float для денег, копия ролей, print-логгер
│   ├── tests.py           # интеграционные тесты + тесты, фиксирующие уязвимости
│   └── migrations/0001_initial.py   # ⚠️ одна миграция на всё
├── fixtures/demo.json     # демо-пользователи и документ
├── docs/architecture.md   # подробное архитектурное описание
├── schema.yml             # экспорт OpenAPI
├── Dockerfile, docker-compose.yml
└── .env.example           # ⚠️ не читается приложением
```

## API Endpoints

### Authentication
- `POST /api/register/` — регистрация (роль задаёт клиент ⚠️)
- `POST /api/token/` — получить JWT
- `POST /api/token/refresh/`

### Documents
- `GET /api/documents/` — список (сотрудник видит свои, роли manager/lawyer/cfo — все)
- `POST /api/documents/` — создать
- `GET/PUT/PATCH/DELETE /api/documents/{id}/` — ⚠️ без проверки владельца, `status` writable
- `GET /api/documents/search-raw/?search=` — ⚠️ SQL-инъекция

### Workflow
- `POST /api/documents/{id}/submit/` — draft → pending_manager
- `POST /api/documents/{id}/approve/` — `{"comment": "..."}`
- `POST /api/documents/{id}/reject/` — `{"comment": "..."}` (обязателен)
- `GET /api/documents/{id}/approvals/` — ⚠️ SQL прямо во view

### Audit / Archive
- `GET /api/documents/{id}/history/` — история действий
- `POST /api/documents/{id}/archive/` — approved → archived (manager/cfo)
- `GET /api/archive/?order_by=` — ⚠️ инъекция через ORDER BY

## План рефакторинга (на семестр)

### Этап 1: Безопасность (месяц 1)
- [ ] Вынести секреты в `.env`
- [ ] Заменить MD5 на безопасное хеширование
- [ ] Исправить SQL-инъекции
- [ ] Добавить валидацию данных

### Этап 2: Разделение слоёв (месяц 2)
- [ ] Разбить God Class на отдельные сервисы
- [ ] Вынести бизнес-логику из views
- [ ] Добавить транзакции

### Этап 3: Модульный монолит (месяц 3)
- [ ] Разделить на отдельные Django apps
- [ ] Ввести Django permissions
- [ ] Добавить FSM для статусов

### Этап 4: Оптимизация (месяц 4)
- [ ] Внедрить кеширование (Redis)
- [ ] Структурированное логирование
- [ ] Написать тесты (покрытие > 80%)

## Антипаттерны в коде

| Антипаттерн | Местоположение |
|-------------|----------------|
| God Object | `services.py` → `DocumentService` |
| Spaghetti Code | `views.py` — логика смешана |
| Hard Code | Проверка ролей, секреты |
| Magic Numbers | `if amount < 1000` |
| Tight Coupling | Views → Models напрямую |
| No Abstraction | Нет интерфейсов/репозиториев |

## Состояния документа

```
draft → pending_manager → pending_lawyer → pending_cfo → approved → archived
                    ↓            ↓             ↓
                  rejected     rejected     rejected
```

⚠️ **Проблема**: Нет FSM, можно установить любой статус напрямую!

## Тестирование

```bash
python manage.py test apps.documents
```

11 тестов: сценарии согласования по границам сумм (999.99 / 1000 / 10000.01), отклонение, архивация,
а также класс `KnownVulnerabilityTests`, который **фиксирует наличие** уязвимостей (MD5, выбор роли
клиентом, IDOR, прямая установка статуса, SQL-инъекция). После рефакторинга эти тесты должны быть
инвертированы.

Что сложно тестировать из-за текущей архитектуры:
- God Class — нельзя изолировать логику согласования от ORM
- Прямые SQL — нужна реальная БД, на SQLite и Postgres поведение инъекций различается
- Хардкод ролей — нужны реальные пользователи с каждой ролью
- Глобальный `service` без DI — нельзя подменить зависимости

## Лицензия

MIT (для учебных целей)

## Авторы

Создано как учебный проект для демонстрации архитектурных антипаттернов и процесса рефакторинга.
