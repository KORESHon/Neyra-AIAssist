<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

# Security Checklist для плагинов

- Секреты только из env.
- Валидация входных данных.
- Ограничение сетевых/файловых операций.
- Явные таймауты для внешних вызовов.
- Логировать ошибки без утечки секретов.
- Для webhook-плагинов включать подписи/nonce/replay checks.