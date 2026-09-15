from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.v1.budgets import router as budgets_router
from app.api.v1.hierarchy import router as hierarchy_router
from app.api.v1.subscriptions import router as subscriptions_router
from app.api.v1.usage import router as usage_router
from app.telemetry import create_telemetry_provider


class HealthResponse(BaseModel):
    status: str


app = FastAPI(title="GenAI Token Management Dashboard API")
telemetry_provider = create_telemetry_provider()
app.include_router(hierarchy_router, prefix="/api/v1")
app.include_router(subscriptions_router, prefix="/api/v1")
app.include_router(usage_router, prefix="/api/v1")
app.include_router(budgets_router, prefix="/api/v1")


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    field_errors = [
        {
            "field": (
                "request"
                if request.url.path.startswith("/api/v1/members/")
                and any(
                    token in str(error["loc"]).lower() for token in ("key", "secret")
                )
                else ".".join(str(part) for part in error["loc"] if part != "body")
            ),
            "message": (
                "Request contains a prohibited field."
                if request.url.path.startswith("/api/v1/members/")
                and any(
                    token in str(error["loc"]).lower() for token in ("key", "secret")
                )
                else error["msg"]
            ),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request validation failed.",
            "field_errors": field_errors,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and {"error", "message", "field_errors"} <= exc.detail.keys():
        content = exc.detail
    else:
        content = {"error": "http_error", "message": str(exc.detail), "field_errors": []}
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


@app.get("/api/v1/system/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
