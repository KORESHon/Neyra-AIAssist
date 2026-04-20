# Продакшн деплой (базовый чеклист)

- Запускать под process manager (systemd/supervisor/pm2 wrapper).
- Включить `INTERNAL_API_TOKEN`.
- Использовать reverse proxy с TLS.
- Ограничить входящий доступ к API.
- Настроить регулярный backup и наблюдение по health/status log.
- Фиксировать версии зависимостей и проверять smoke после обновлений.
