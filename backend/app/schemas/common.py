from typing import Generic, TypeVar

from pydantic import BaseModel, Field

SchemaType = TypeVar("SchemaType")


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