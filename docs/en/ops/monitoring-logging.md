<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

# Мониторинг и логи

- Health monitor: `core/health_monitor.py`.
- Статус отчёты: `logs/health_status.jsonl`.
- Системные логи: путь из `logging.system_log`.
- Диалоговые логи: путь из `logging.chat_log`.

Для алертов в интеграции используйте webhook routes и отслеживайте `deliveries`/`dlq`.