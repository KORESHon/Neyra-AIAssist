# Neyra Frontend

React + Vite приложение, которое обслуживается тем же FastAPI процессом (`python main.py`).

## Разделы UI

- `Home` — микро-сайт и обзор возможностей.
- `Dashboard` — health, память, баланс, список плагинов.
- `Plugins` — управление состоянием плагинов, редактирование plugin config, invoke/reload/restart.
- `Settings` — Bearer token и runtime allowlist update.
- `Webhooks` — маршруты outbound, тесты, deliveries/DLQ.
- `API Docs` — встроенный Swagger/ReDoc + openapi.json.

## Разработка

```bash
cd frontend
npm install
npm run dev
```

Proxy на backend настраивается в `vite.config.ts` (`/v1`, `/docs`, `/redoc`, `/openapi.json`).

## Сборка

```bash
cd frontend
npm run build
```

Сборка попадает в `frontend/dist` и раздаётся из Internal API.
