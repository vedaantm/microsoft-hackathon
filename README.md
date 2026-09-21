# GenAI Token Management Dashboard

## Start locally

Copy `.env.example` to `.env` at the repository root and replace the placeholder values before starting the stack. The dashboard requires real values for `AUTH_MODE`, `SESSION_SECRET`, and `TELEMETRY_SOURCE`; the local gateway additionally requires real values for `GATEWAY_LLM_API_KEY`, `GATEWAY_LLM_BASE_URL`, and `GATEWAY_LLM_MODEL`.

For local development, set `AUTH_MODE=development` exactly. The dev-login endpoint returns `404` for any other value, including an unset, empty, or differently-cased value. Docker Compose reads these variables from the host environment, so provide them either in the root `.env` file or by exporting/setting them in your shell before running Compose.

```sh
docker compose up --build
```

The frontend is available at http://localhost:5173 and the backend health check is available at http://localhost:8000/api/v1/system/health.

Local development uses seed-data mode by default. The local gateway is the live/demo request path for OpenAI-compatible chat completions; it forwards employee prompts to the configured third-party provider and records the returned usage in PostgreSQL. Set these three variables before using it:

```text
GATEWAY_LLM_API_KEY=
GATEWAY_LLM_BASE_URL=
GATEWAY_LLM_MODEL=
```

`AzureMonitorTelemetryProvider` exists in the code as the intended Azure integration, but its queries were never completed or verified. It is not a working production telemetry path.

## Database migrations and seed data

`docker compose up --build` starts PostgreSQL and waits for its healthcheck before starting the backend. In a second shell, apply the full migration chain and load the sample fixtures:

```powershell
docker compose exec backend alembic upgrade head
docker compose exec backend python scripts/seed.py
```

The default Docker database is PostgreSQL, persisted in the named `postgres-data` volume. To reset it and start from a genuinely fresh database, run `docker compose down -v` before bringing the stack up again.

For fast local development outside Docker, SQLite remains supported. From the repository root, create the SQLite schema and load the sample fixtures with:

```powershell
cd backend
alembic upgrade head
$env:PYTHONPATH='.'
python scripts/seed.py
```

For bash or other Unix-like shells, use:

```sh
cd backend
alembic upgrade head
PYTHONPATH=. python scripts/seed.py
```

The default non-Docker database is `sqlite:///./genai_dashboard.db`; set `DATABASE_URL` to use another SQLAlchemy-supported database.

The backend test suite intentionally uses temporary SQLite databases for speed and isolation. The PostgreSQL migration chain is additionally exercised against the real Compose database; the application-level budget-overlap check is tested through the API and no longer depends on a SQLite trigger.

## Phase 6 items deliberately omitted

The following original Phase 6 items remain outside this implementation: Models and prices CRUD, Azure connection status, live Azure Monitor data, and the planned Azure handoff and smoke-test workflow. Alerts and audit events are not omitted; they were implemented in Phase 7.
