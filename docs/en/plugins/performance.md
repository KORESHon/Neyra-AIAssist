<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

# Performance рекомендации

- Не держите тяжёлые синхронные циклы в resident plugin без sleep/backoff.
- Сокращайте payload в event bus и webhook отправках.
- Для webhook delivery отслеживайте latency и ошибки в `deliveries`.
- Ограничивайте размер входных сообщений и вложений.