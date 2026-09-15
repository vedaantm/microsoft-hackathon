from fastapi import FastAPI
from pydantic import BaseModel

from app.telemetry import create_telemetry_provider


class HealthResponse(BaseModel):
    status: str


app = FastAPI(title="GenAI Token Management Dashboard API")
telemetry_provider = create_telemetry_provider()


@app.get("/api/v1/system/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
