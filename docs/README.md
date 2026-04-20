# Neyra Documentation Portal

## Навигация

### Архитектура
- [Обзор архитектуры](architecture/overview.md)
- [Режимы рантайма](architecture/runtime-modes.md)
- [Модель конфигурации](architecture/configuration-model.md)
- [Модель безопасности](architecture/security-model.md)

### Установка и конфигурация
- [Быстрый старт](setup/quickstart.md)
- [Переменные окружения](setup/environment-variables.md)
- [Справочник config.yaml](setup/config-reference.md)

### Эксплуатация
- [Локальный деплой](ops/deployment-local.md)
- [Прод-деплой](ops/deployment-production.md)
- [Мониторинг и логи](ops/monitoring-logging.md)
- [Бэкап и восстановление](ops/backup-restore.md)
- [Troubleshooting](ops/troubleshooting.md)
- [WSS deploy](wss-deploy.md)

### API
- [API overview](api/overview.md)
- [REST endpoints](api/rest.md)
- [WebSocket chat](api/websocket-chat.md)
- [WebSocket audio](api/websocket-audio.md)
- [Ошибки API](api/errors.md)
- [Примеры запросов](api/examples.md)
- [OpenAPI / Swagger / ReDoc](api/openapi.md)

### Использование Neyra
- [Гайд пользователя](usage/end-user-guide.md)
- [Гайд администратора](usage/admin-guide.md)
- [Гайд интегратора](usage/integration-guide.md)
- [FAQ](usage/faq.md)

### Плагины и SDK
- [Plugin system overview](plugins/overview.md)
- [Getting started](plugins/getting-started.md)
- [Manifest reference](plugins/manifest-reference.md)
- [SDK reference](plugins/sdk-reference.md)
- [Config и секреты плагинов](plugins/config-secrets.md)
- [События и конкурентность](plugins/events-concurrency.md)
- [Тестирование плагинов](plugins/testing.md)
- [Security checklist](plugins/security-checklist.md)
- [Performance рекомендации](plugins/performance.md)
- [Версионирование и совместимость](plugins/versioning-compatibility.md)
- [Публикация плагинов](plugins/publishing.md)
- Cookbook:
  - [Webhook plugin](plugins/cookbook/webhook-plugin.md)
  - [Background worker plugin](plugins/cookbook/background-worker.md)

## Документация в интерфейсе

В веб-панели Neyra есть встроенный раздел **API Docs**, который отображает `/docs` и `/redoc` прямо в UI, а также даёт доступ к `/openapi.json`.
