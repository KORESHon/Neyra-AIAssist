# Troubleshooting

## API не отвечает
- Проверьте, что `python main.py` запущен.
- Проверьте host/port в `interfaces/internal_api/config.yaml`.

## 401 Unauthorized
- Либо задайте корректный Bearer, либо очистите `INTERNAL_API_TOKEN`.

## Discord plugin не стартует
- Проверьте `interfaces/discord_text/plugin.yaml` (`enabled: true`).
- Проверьте `DISCORD_TOKEN` в `.env`.

## Ошибки вебхуков
- Смотрите `/v1/webhooks/deliveries` и `/v1/webhooks/dlq`.
- Проверьте `target_url`, secret и сетевую доступность endpoint-а.
