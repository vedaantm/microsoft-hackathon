from collections.abc import Generator

from fastapi import HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.schemas import PageParams


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def page_params(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100)
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


def commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "error": "unique_constraint_violation",
                "message": "The resource conflicts with an existing record.",
                "field_errors": [],
            },
        ) from exc


def get_or_404(db: Session, model: type, resource_id: int):
    resource = db.get(model, resource_id)
    if resource is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": "Resource was not found.",
                "field_errors": [],
            },
        )
    return resource