# Мониторинг и логи

- Health monitor: `core/health_monitor.py`.
- Статус отчёты: `logs/health_status.jsonl`.
- Системные логи: путь из `logging.system_log`.
- Диалоговые логи: путь из `logging.chat_log`.

Для алертов в интеграции используйте webhook routes и отслеживайте `deliveries`/`dlq`.
