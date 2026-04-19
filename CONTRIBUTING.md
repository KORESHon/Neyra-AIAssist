# Contributing

Thanks for contributing to Neyra.

## Development setup

1. Create venv:
   - `python -m venv .venv`
   - `.venv\Scripts\activate`
2. Install deps:
   - `pip install -r requirements.txt`
3. Create `.env` from `.env.example`.
4. Run healthcheck:
   - `.venv\Scripts\python.exe scripts\healthcheck.py`

## Scope and architecture

- Keep runtime model-first.
- Do not add Discord voice receive/send into stable path.
- New interface work should go to `interfaces/` as isolated plugins; see `interfaces/000EXAMPLE/HELP.md` (Plugin SDK, RU + EN).
- Keep secrets out of code and config defaults; use `.env`.

## Code style

- Prefer simple, explicit Python.
- Keep comments short and practical.
- Avoid unrelated refactors in the same change.

## Before opening PR

- Run syntax checks / tests you changed.
- Run healthcheck script.
- Update docs (`README.md`, `PLAN.md`, `.env.example`) if behavior changed.

