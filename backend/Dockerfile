FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY backend/pyproject.toml .
RUN pip install --no-cache-dir ".[dev]"

COPY backend/app ./app
COPY backend/tests ./tests
COPY backend/alembic.ini .
COPY backend/alembic ./alembic
COPY backend/scripts ./scripts
COPY sample-data ./sample-data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
