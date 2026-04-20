# Quickstart

1. Создайте venv и установите зависимости:
   - `python -m venv .venv`
   - `.venv\\Scripts\\activate` (Windows)
   - `pip install -r requirements.txt`
2. Скопируйте `.env.example` -> `.env` и заполните ключи.
3. Скопируйте `config.example.yaml` -> `config.yaml`.
4. Для плагинов скопируйте:
   - `interfaces/discord_text/config.example.yaml` -> `config.yaml`
   - `interfaces/internal_api/config.example.yaml` -> `config.yaml`
5. (опционально) frontend:
   - `cd frontend && npm install && npm run build`
6. Запуск:
   - `python main.py`
