from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.v1.common import get_db
from app.models import BudgetPolicy, Department, Member, Team
from app.telemetry import TelemetryFilters

router = APIRouter()
SESSION_COOKIE = "genai_session"
ROLES = {"org_admin", "department_manager", "team_manager", "member"}
logger = logging.getLogger(__name__)


class DevLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str | int | None = None
    member_id: int | None = None
    email: str | None = None


@dataclass(frozen=True)
class Identity:
    member_id: int
    name: str
    email: str
    role: str
    organization_id: int
    department_id: int
    team_id: int

    @classmethod
    def from_member(cls, member: Member) -> Identity:
        return cls(
            member_id=member.id,
            name=member.name,
            email=member.email,
            role=member.role,
            organization_id=member.organization_id,
            department_id=member.department_id,
            team_id=member.team_id,
        )


def _http_error(
    status_code: int, message: str, error: str = "authorization_error"
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": error, "message": message, "field_errors": []},
    )


def _secret() -> bytes:
    return _SESSION_SECRET.encode() if _SESSION_SECRET else _PROCESS_SECRET


_SESSION_SECRET = os.getenv("SESSION_SECRET")
_PROCESS_SECRET = secrets.token_bytes(32)
if not _SESSION_SECRET:
    logger.warning(
        "SESSION_SECRET is unset; using a random per-process session secret. "
        "Sessions will be invalidated when the process restarts."
    )


def _encode_session(identity: Identity) -> str:
    payload = json.dumps(
        {"member_id": identity.member_id, "role": identity.role},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(_secret(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _decode_session(token: str) -> dict[str, object]:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(_secret(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        claims = json.loads(payload)
        if not isinstance(claims, dict) or not isinstance(claims.get("member_id"), int):
            raise ValueError
        if not isinstance(claims.get("role"), str) or claims["role"] not in ROLES:
            raise ValueError
        return claims
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise _http_error(401, "A valid session is required.", "authentication_error") from None


def get_current_identity(
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    db: Session = Depends(get_db),
) -> Identity:
    if session_token is None:
        raise _http_error(401, "A valid session is required.", "authentication_error")
    claims = _decode_session(session_token)
    member = db.get(Member, claims["member_id"])
    if member is None or member.status != "active" or member.role != claims["role"]:
        raise _http_error(401, "A valid session is required.", "authentication_error")
    return Identity.from_member(member)


def require_role(*roles: str) -> Callable:
    def dependency(identity: Identity = Depends(get_current_identity)) -> Identity:
        if roles and identity.role not in roles:
            raise _http_error(403, "Your role does not permit this action.")
        return identity

    return dependency


CurrentIdentity = Annotated[Identity, Depends(get_current_identity)]


def _forbidden() -> HTTPException:
    return _http_error(403, "The requested resource is outside your permitted scope.")


def ensure_scope(
    identity: Identity,
    db: Session,
    *,
    organization_id: int | None = None,
    department_id: int | None = None,
    team_id: int | None = None,
    member_id: int | None = None,
) -> None:
    if organization_id is not None and organization_id != identity.organization_id:
        raise _forbidden()
    if department_id is not None:
        department = db.get(Department, department_id)
        if department is None or department.organization_id != identity.organization_id:
            raise _forbidden()
        if identity.role == "department_manager" and department_id != identity.department_id:
            raise _forbidden()
        if identity.role in {"team_manager", "member"} and department_id != identity.department_id:
            raise _forbidden()
    if team_id is not None:
        team = db.get(Team, team_id)
        if team is None or team.organization_id != identity.organization_id:
            raise _forbidden()
        if identity.role == "department_manager" and team.department_id != identity.department_id:
            raise _forbidden()
        if identity.role in {"team_manager", "member"} and team_id != identity.team_id:
            raise _forbidden()
    if member_id is not None:
        member = db.get(Member, member_id)
        if member is None or member.organization_id != identity.organization_id:
            raise _forbidden()
        if identity.role == "department_manager" and member.department_id != identity.department_id:
            raise _forbidden()
        if identity.role == "team_manager" and member.team_id != identity.team_id:
            raise _forbidden()
        if identity.role == "member" and member_id != identity.member_id:
            raise _forbidden()


def scoped_filters(identity: Identity, db: Session, filters: TelemetryFilters) -> TelemetryFilters:
    ensure_scope(
        identity,
        db,
        organization_id=filters.organization_id,
        department_id=filters.department_id,
        team_id=filters.team_id,
        member_id=filters.member_id,
    )
    values = {
        "organization_id": filters.organization_id or identity.organization_id,
        "department_id": filters.department_id,
        "team_id": filters.team_id,
        "member_id": filters.member_id,
    }
    if identity.role == "department_manager":
        values["department_id"] = filters.department_id or identity.department_id
    elif identity.role == "team_manager":
        values["team_id"] = filters.team_id or identity.team_id
    elif identity.role == "member":
        values["member_id"] = filters.member_id or identity.member_id
    return TelemetryFilters(
        **{**filters.__dict__, **values}
    )


def ensure_budget_scope(identity: Identity, db: Session, policy: BudgetPolicy) -> None:
    if policy.scope_type == "organization":
        ensure_scope(identity, db, organization_id=policy.scope_id)
    elif policy.scope_type == "department":
        ensure_scope(identity, db, department_id=policy.scope_id)
    elif policy.scope_type == "team":
        ensure_scope(identity, db, team_id=policy.scope_id)
    elif policy.scope_type == "member":
        ensure_scope(identity, db, member_id=policy.scope_id)
    else:
        raise _forbidden()
    if policy.organization_id != identity.organization_id:
        raise _forbidden()


def budget_is_visible(identity: Identity, policy: BudgetPolicy) -> bool:
    if policy.organization_id != identity.organization_id:
        return False
    if identity.role == "org_admin":
        return True
    if identity.role == "department_manager":
        return policy.scope_type == "department" and policy.scope_id == identity.department_id or (
            policy.scope_type == "team" and policy.scope_id == identity.team_id
        ) or (policy.scope_type == "member" and policy.scope_id == identity.member_id)
    if identity.role == "team_manager":
        return policy.scope_type == "team" and policy.scope_id == identity.team_id or (
            policy.scope_type == "member" and policy.scope_id == identity.member_id
        )
    return policy.scope_type == "member" and policy.scope_id == identity.member_id


def _member_for_identifier(db: Session, identifier: str | int) -> Member | None:
    if isinstance(identifier, int) or identifier.isdigit():
        return db.get(Member, int(identifier))
    return db.query(Member).filter(Member.email == identifier).first()


@router.post("/auth/dev-login")
def dev_login(payload: DevLoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    if os.getenv("AUTH_MODE") != "development":
        raise _http_error(404, "Resource was not found.", "not_found")
    identifier = payload.identifier
    if identifier is None:
        identifier = payload.member_id if payload.member_id is not None else payload.email
    if identifier is None:
        raise _http_error(404, "Member was not found.", "not_found")
    member = _member_for_identifier(db, identifier)
    if member is None or member.status != "active" or member.role not in ROLES:
        raise _http_error(404, "Member was not found.", "not_found")
    identity = Identity.from_member(member)
    response.set_cookie(
        SESSION_COOKIE,
        _encode_session(identity),
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return {"member_id": identity.member_id, "role": identity.role}


@router.get("/auth/me")
def auth_me(identity: CurrentIdentity) -> dict:
    scope = {
        "organization_id": identity.organization_id,
        "department_id": identity.department_id,
        "team_id": identity.team_id,
        "member_id": identity.member_id,
    }
    return {
        "member_id": identity.member_id,
        "name": identity.name,
        "email": identity.email,
        "role": identity.role,
        "scope": scope,
        **scope,
    }


@router.post("/auth/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)
