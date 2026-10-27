# PortaGraph

Интеллектуальная система анализа и визуализации программных проектов. Подключаете несколько Git-репозиториев, и PortaGraph анализирует их как единую систему:

- определяет назначение каждого репозитория и сервиса;
- строит граф архитектуры и зависимостей;
- отвечает на вопросы по коду со ссылками на файлы и строки;
- оценивает последствия изменений (impact analysis);
- готовит материалы для онбординга.

Учебный проект по дисциплине «Программная инженерия», группа ПИ24, КубГАУ.
Команда: **Казанкова Анастасия** (тимлид, backend и архитектура) и **Чиженко Максим** (AI/агентная система, анализ кода, frontend).

## Стек

| Слой | Технологии |
|---|---|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS, React Flow (`@xyflow/react`), dagre |
| Backend | Java 21, Spring Boot 3.3, Spring Data JPA / Hibernate 6, Spring Security (JWT) |
| Данные | PostgreSQL 16 + pgvector, Redis, MinIO (S3) |
| AI | агентное ядро Hermes, LLM API (OpenAI-совместимый), RAG по коду и документации |
| Анализ кода | Tree-sitter (воркер), резервный `SymbolExtractor`, GitHub/Bitbucket API, webhooks |
| Инфраструктура | Docker Compose, Nginx, GitHub Actions |

## Структура

```
backend/
  src/main/java/ru/portagraph/
    core/          алгоритмы без зависимостей от Spring: граф, impact analysis,
                   маскирование секретов, нарезка кода, роли репозиториев, связи
    domain/        JPA-сущности и перечисления
    repository/    Spring Data репозитории (в т.ч. векторный поиск pgvector)
    service/       бизнес-логика: подключение, индексация, анализ, RAG, документы
    agent/         адаптер агентного ядра Hermes и клиент embeddings
    integration/   клиенты GitHub и Bitbucket
    web/           REST-контроллеры и DTO
  src/main/resources/db/migration/   миграции Flyway
frontend/          Next.js: список проектов, карта системы (React Flow), AI-ассистент
deploy/            конфигурация Nginx
```

## Запуск

```bash
cp .env.example .env        # заполнить JWT_SECRET, CREDENTIAL_KEY, ключи LLM/Hermes
docker compose up --build   # http://localhost
```

Тесты backend: `mvn -f backend/pom.xml test`.

## Основные эндпоинты API

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/auth/register`, `/api/auth/login` | регистрация, вход (JWT) |
| GET/POST | `/api/projects` | список и создание проектов |
| POST | `/api/projects/{id}/repositories` | подключить набор репозиториев |
| GET/POST | `/api/projects/{id}/analysis` | прогресс и перезапуск анализа |
| GET | `/api/projects/{id}/graph?mode=overview\|detailed` | граф для визуализации |
| POST | `/api/projects/{id}/graph/nodes/{nodeId}/verify` | подтвердить вывод агента |
| POST | `/api/projects/{id}/assistant/ask` | вопрос AI-ассистенту |
| POST | `/api/projects/{id}/impact` | impact analysis изменения |
| GET/POST | `/api/projects/{id}/documents` | архитектурные описания и онбординг |
| POST | `/api/webhooks/{github\|bitbucket}/{repoId}` | синхронизация по push |

Документация OpenAPI после запуска доступна по адресу `/swagger-ui.html`.
