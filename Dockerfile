# Neyra core: HTTP API + дашборд + resident-плагины (см. main.py).
# Сборка: docker compose build
# Память/Chroma и логи — через volumes в docker-compose.yml.
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8787

CMD ["python", "main.py"]
