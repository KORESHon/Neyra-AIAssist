# Neyra - AIAssist

![AI Assisted](https://img.shields.io/badge/AI_Assisted-Code_Generation-000000?style=for-the-badge&logo=openai&logoColor=white)

**Репозиторий:** [github.com/KORESHon/Neyra-AIAssist](https://github.com/KORESHon/Neyra-AIAssist)

Модульная платформа ИИ-ассистента с приоритетом на стабильное ядро.

## Обзор

Neyra строится как переиспользуемое ядро плюс подключаемые интеграции.

Ключевые цели:

- стабильное ядро (`LLM + Memory + Reflection + Tools`),
- поддержка облачных и локальных backend,
- событийная интеграция и webhooks,
- расширяемость через плагины без переписывания ядра.

Текущий стабильный runtime:

- режим `model` (консоль/ядро),
- интерфейс `discord_text` (текст + изображения).

## Архитектура (кратко)

- `core/` — модель, память, рефлексия, инструменты, загрузка секретов.
- `core/voice/` — voice-адаптеры и будущие фабрики STT/TTS.
- `interfaces/` — плагины (`interfaces/<id>/plugin.yaml` + `main.py`): discord, API, local voice, screen и шаблон **`000EXAMPLE`** (первый в списке по имени папки).
- **Документация Plugin SDK** — [HELP-RU.md](interfaces/000EXAMPLE/HELP-RU.md) (русский туториал), [HELP.md](interfaces/000EXAMPLE/HELP.md) (English).
- `scripts/` — эксплуатационные скрипты (healthcheck и вспомогательные утилиты).
- `main.py` — точка входа и запуск режимов.
- `run_neyra.bat` — запуск на Windows с preflight-проверками.

## Продуктовый вектор

Neyra развивается как персональный публичный ассистент:

- desktop-приложение ассистента с управлением ОС (через безопасные политики),
- mobile-lite клиент (чат/уведомления через API),
- микро-сайт с дашбордом, статусами и документацией API,
- внешние хранилища (в первую очередь Google Drive) для backup/restore,
- модульное расширение (voice/screen/music/plugins).

Форм-фактор “ИИ-станции” оставлен в future backlog и не входит в текущую реализацию.

## Быстрый старт (Windows)

1. Создай и активируй venv:
  - `python -m venv .venv`
  - `.venv\Scripts\activate`
2. Установи зависимости:
  - `pip install -r requirements.txt`
3. Создай `.env` из `.env.example` и заполни секреты.
4. Создай `config.yaml` из `config.example.yaml`.
5. Запусти preflight:
  - `.venv\Scripts\python.exe scripts\healthcheck.py`
6. Запуск:
  - `run_neyra.bat`
  - или `.venv\Scripts\python.exe main.py --mode model`

## Режимы запуска

- `model` — основной режим (ядро/консоль).
- `discord` — текстовый Discord-бот.
- `local_voice` — заготовка локального голосового интерфейса.
- `screen` — заготовка screen-интерфейса.

## 💖 Поддержать проект

Если вам нравится проект и вы хотите поддержать его развитие (или просто скинуть автору на кофе), вы можете сделать это через криптовалюту. Адреса совпадают с кошельками в Trust Wallet и TG Wallet.

- **TON (сеть: TON):** `UQD6p87_YQNeZmGduBHnkWBF3AbvyNOwt_xt8fn1Vd3zBSYa`
- **USDT (сеть: TON):** `UQD6p87_YQNeZmGduBHnkWBF3AbvyNOwt_xt8fn1Vd3zBSYa`
- **USDT (сеть: TRC20):** `TU467q2tsQLH58u6KVh3LyGwx7sqn2WyPQ`
- **USDT (сеть: ERC20):** `0xf834f04668b947eeb56b433c54173f311a06392a`
- **ETH (Ethereum Mainnet):** `0xf834f04668b947eeb56b433c54173f311a06392a`
- **BTC (Bitcoin Network):** `bc1qevu7yty2l4u3n54gjkvj9nrtypj303ejd7e0z3`

*Обязательно проверяйте сеть при отправке! Спасибо за вашу поддержку 🚀*

Ядро остаётся open-source под лицензией MIT независимо от донатов.

## О роли ИИ в проекте (AI-assisted development)

Этот проект — практическое исследование в области **prompt engineering** и взаимодействия со сложными ИИ-системами в реальном коде.

- **Архитектура, системный дизайн и интеграция модулей** спроектированы и направляются человеком.
- **Рутинный код, обвязка и значительная часть реализации** выполнялись с активным использованием AI-агентов (Cursor, LLM-ассистенты).

Я считаю, что будущее разработки — это синергия человека-архитектора и ИИ-реализации. Если вы найдёте неоптимальные или шероховатые сгенерированные участки — открывайте Issue или PR: код-ревью от живых разработчиков только приветствуется.

## Файлы планирования и документации

- `README.md` — публичный обзор (EN).
- `README-RU.md` — публичный обзор (RU).
- `PLAN.md` — дорожная карта (если ведёте в репозитории).
- **Как писать плагины** — [HELP-RU.md](interfaces/000EXAMPLE/HELP-RU.md), [HELP.md](interfaces/000EXAMPLE/HELP.md).

