from datetime import datetime, timezone
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, Field, PlainSerializer

SchemaType = TypeVar("SchemaType")


def _serialize_utc_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[
    datetime,
    PlainSerializer(_serialize_utc_datetime, return_type=str),
]


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class PaginatedResponse(BaseModel, Generic[SchemaType]):
    items: list[SchemaType]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    error: str
    message: str
    field_errors: list[dict[str, str]] = Field(default_factory=list)