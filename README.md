# GenAI Token Management Dashboard

## Start locally

```sh
docker compose up --build
```

The frontend is available at http://localhost:5173 and the backend health check is available at http://localhost:8000/api/v1/system/health.

## Database seed data

From the repository root, create the local SQLite schema and load the sample fixtures with:

```sh
cd backend
alembic upgrade head
PYTHONPATH=. python scripts/seed.py
```

The default database is `sqlite:///./genai_dashboard.db`; set `DATABASE_URL` to use another SQLAlchemy-supported database.
