# Agent Instructions — smarthome_floorplan

Hybrid app: a Vue 3 + Vite frontend (repo root) and a Python FastAPI backend
(`server/`) that serves the built frontend, bridges zigbee2mqtt over MQTT, and
authenticates via a signed HttpOnly session cookie. The Docker image builds the
frontend, then runs the backend serving the static assets.

## Project structure
- `src/` — Vue 3 + Vite + TypeScript frontend (PWA); vitest specs sit next to the code (`*.test.ts`).
- `e2e/` — Playwright suite (`npm run test:e2e`), not run in CI.
- `server/main.py` — thin backend entry point.
- `server/src/` — backend code (`settings.py`, `api.py`, `config_store.py`, `mqtt_client.py`).
- `server/tests/` — pytest suite for the backend.
- `ci/smoke.py` — smoke gate run by CI against the built image.
- `data/` — runtime state (config, custom icon); gitignored, mounted as a docker volume.
- `docker-compose.yml` — readable record of the deployed Portainer stack (placeholders only).
- Built frontend assets are copied into `server/static/` inside the image (not in git).

`server/` is the Python "app root": in the image its contents land in `/app`, so
relative paths (`.env`, `data/`) resolve at the repo root in dev and under `/app`
in the container.

## Setup
```bash
make install           # create .venv and install backend dev/test deps
cp .env.example .env   # fill in AUTH_PASSWORD and MQTT_HOST
npm ci                 # frontend deps
```

## Running tests
```bash
make test              # backend (pytest)
npm test               # frontend (vitest)
```

## Running locally
```bash
make run               # backend (API) on :8000
make dev               # Vite frontend dev server (proxies /api to :8000)
make build             # frontend into dist/
```
For local HTTP dev set `COOKIE_SECURE=false` in `.env` (otherwise the session
cookie is Secure-only and the browser drops it over http).

## CI and deploy (Gitea Actions)
- `.gitea/workflows/tests.yml` — PR gate: backend and frontend tests, image build,
  `ci/smoke.py`. No secrets, no push.
- `.gitea/workflows/image-check-publish.yml` — on push to `main`: the same tests, build
  and smoke gate, then pushes `:<sha>` and `:latest` to the Gitea registry.
- Production follows `:latest` via Portainer auto-update with no manual approval, so the
  smoke gate is the last check before rollout. The test jobs in both workflows must stay
  identical.

## Conventions
- All runtime state lives in `data/`.
- All configuration/secrets come from ENV / `.env` (see `.env.example`), read via
  `server/src/settings.py` (`pydantic-settings`). Credentials and own-service
  addresses (`AUTH_PASSWORD`, `MQTT_HOST`) have no defaults — missing → fail at start.
- Credentials/addresses the user provides go ONLY into `.env` (never into code,
  never via inline env vars), read through `Settings`.
- Comments in code are in English.
- Routine tasks go through `make` targets (`install` / `test` / `run` / `dev` / `build`).
- Tests are required for backend code; in CI the image build depends on the tests.

## Limits for agents
- Tests: at most three times the code (`wc -l` of `tests/` against the code). Over the limit,
  still write the test you need, and in the same change go through the old tests: drop or merge
  duplicates and tests of implementation rather than behaviour.
- Comments explain the code as it is and why it is built this way. History ("used to", "after
  the review", "since the incident") goes into the commit message.
- This file stays under ~150 lines: only what an agent would get wrong without it. No decision
  history, incident logs or retelling of the code.
