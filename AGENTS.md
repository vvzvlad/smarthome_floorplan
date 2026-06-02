# Agent Instructions — smarthome_floorplan

Hybrid app: a Vue 3 + Vite frontend (repo root) and a Python FastAPI backend
(`server/`) that serves the built frontend, bridges zigbee2mqtt over MQTT, and
authenticates via a signed HttpOnly session cookie. The Docker image builds the
frontend, then runs the backend serving the static assets.

## Project structure
- `src/` — Vue 3 + Vite + TypeScript frontend (PWA).
- `server/main.py` — thin backend entry point.
- `server/src/` — backend code (`settings.py`, `api.py`, `config_store.py`, `mqtt_client.py`).
- `server/tests/` — pytest suite for the backend.
- `data/` — runtime state (config, custom icon); gitignored, mounted as a docker volume.
- Built frontend assets are copied into `server/static/` inside the image (not in git).

`server/` is the Python "app root": in the image its contents land in `/app`, so
relative paths (`.env`, `data/`) resolve at the repo root in dev and under `/app`
in the container.

## Setup
```bash
make install           # create .venv and install backend dev/test deps
cp .env.example .env   # fill in AUTH_PASSWORD and MQTT_HOST
```

## Running tests
```bash
make test
```

## Running locally
```bash
make run               # backend (API) on :8000
make dev               # Vite frontend dev server (proxies /api to :8000)
```
For local HTTP dev set `COOKIE_SECURE=false` in `.env` (otherwise the session
cookie is Secure-only and the browser drops it over http).

## Conventions
- All runtime state lives in `data/`.
- All configuration/secrets come from ENV / `.env` (see `.env.example`), read via
  `server/src/settings.py` (`pydantic-settings`). Credentials and own-service
  addresses (`AUTH_PASSWORD`, `MQTT_HOST`) have no defaults — missing → fail at start.
- Credentials/addresses the user provides go ONLY into `.env` (never into code,
  never via inline env vars), read through `Settings`.
- Comments in code are in English.
- Routine tasks go through `make` targets (`install` / `test` / `run` / `dev` / `build`).
- Tests are required for backend code; in CI `build` depends on `test`.
