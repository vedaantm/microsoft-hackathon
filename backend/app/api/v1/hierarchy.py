from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.common import commit, get_db, get_or_404, page_params
from app.models import Department, Member, Organization, Team
from app.schemas import (
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    MemberCreate,
    MemberRead,
    MemberUpdate,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    PageParams,
    PaginatedResponse,
    TeamCreate,
    TeamRead,
    TeamUpdate,
)

router = APIRouter()
# TODO(Phase 5): enforce role-based authorization


def validation_error(message: str, field: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "error": "validation_error",
            "message": message,
            "field_errors": [{"field": field, "message": message}],
        },
    )


def paginated(query, params: PageParams) -> dict:
    total = query.count()
    items = query.offset((params.page - 1) * params.page_size).limit(params.page_size).all()
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


@router.get("/organizations", response_model=PaginatedResponse[OrganizationRead])
def list_organizations(
    params: PageParams = Depends(page_params), db: Session = Depends(get_db)
) -> dict:
    return paginated(db.query(Organization).order_by(Organization.id), params)


@router.post("/organizations", response_model=OrganizationRead, status_code=201)
def create_organization(payload: OrganizationCreate, db: Session = Depends(get_db)) -> Organization:
    organization = Organization(**payload.model_dump())
    db.add(organization)
    commit(db)
    db.refresh(organization)
    return organization


@router.get("/organizations/{organization_id}", response_model=OrganizationRead)
def get_organization(organization_id: int, db: Session = Depends(get_db)) -> Organization:
    return get_or_404(db, Organization, organization_id)


@router.patch("/organizations/{organization_id}", response_model=OrganizationRead)
def update_organization(
    organization_id: int, payload: OrganizationUpdate, db: Session = Depends(get_db)
) -> Organization:
    organization = get_or_404(db, Organization, organization_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(organization, key, value)
    commit(db)
    db.refresh(organization)
    return organization


@router.get(
    "/organizations/{organization_id}/departments",
    response_model=PaginatedResponse[DepartmentRead],
)
def list_departments(
    organization_id: int,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
) -> dict:
    get_or_404(db, Organization, organization_id)
    query = db.query(Department).filter(Department.organization_id == organization_id)
    return paginated(query.order_by(Department.id), params)


@router.post(
    "/organizations/{organization_id}/departments",
    response_model=DepartmentRead,
    status_code=201,
)
def create_department(
    organization_id: int, payload: DepartmentCreate, db: Session = Depends(get_db)
) -> Department:
    get_or_404(db, Organization, organization_id)
    department = Department(organization_id=organization_id, **payload.model_dump())
    db.add(department)
    commit(db)
    db.refresh(department)
    return department


@router.get("/departments/{department_id}", response_model=DepartmentRead)
def get_department(department_id: int, db: Session = Depends(get_db)) -> Department:
    return get_or_404(db, Department, department_id)


@router.patch("/departments/{department_id}", response_model=DepartmentRead)
def update_department(
    department_id: int, payload: DepartmentUpdate, db: Session = Depends(get_db)
) -> Department:
    department = get_or_404(db, Department, department_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(department, key, value)
    commit(db)
    db.refresh(department)
    return department


@router.get("/departments/{department_id}/teams", response_model=PaginatedResponse[TeamRead])
def list_teams(
    department_id: int,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
) -> dict:
    get_or_404(db, Department, department_id)
    query = db.query(Team).filter(Team.department_id == department_id)
    return paginated(query.order_by(Team.id), params)


@router.post("/departments/{department_id}/teams", response_model=TeamRead, status_code=201)
def create_team(
    department_id: int, payload: TeamCreate, db: Session = Depends(get_db)
) -> Team:
    department = get_or_404(db, Department, department_id)
    team = Team(
        organization_id=department.organization_id,
        department_id=department_id,
        **payload.model_dump(),
    )
    db.add(team)
    commit(db)
    db.refresh(team)
    return team


@router.get("/teams/{team_id}", response_model=TeamRead)
def get_team(team_id: int, db: Session = Depends(get_db)) -> Team:
    return get_or_404(db, Team, team_id)


@router.patch("/teams/{team_id}", response_model=TeamRead)
def update_team(team_id: int, payload: TeamUpdate, db: Session = Depends(get_db)) -> Team:
    team = get_or_404(db, Team, team_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(team, key, value)
    commit(db)
    db.refresh(team)
    return team


@router.get("/teams/{team_id}/members", response_model=PaginatedResponse[MemberRead])
def list_members(
    team_id: int,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
) -> dict:
    get_or_404(db, Team, team_id)
    query = db.query(Member).filter(Member.team_id == team_id)
    return paginated(query.order_by(Member.id), params)


@router.post("/teams/{team_id}/members", response_model=MemberRead, status_code=201)
def create_member(team_id: int, payload: MemberCreate, db: Session = Depends(get_db)) -> Member:
    team = get_or_404(db, Team, team_id)
    member = Member(
        organization_id=team.organization_id,
        department_id=team.department_id,
        team_id=team_id,
        **payload.model_dump(),
    )
    db.add(member)
    commit(db)
    db.refresh(member)
    return member


@router.get("/members/{member_id}", response_model=MemberRead)
def get_member(member_id: int, db: Session = Depends(get_db)) -> Member:
    return get_or_404(db, Member, member_id)


@router.patch("/members/{member_id}", response_model=MemberRead)
def update_member(
    member_id: int, payload: MemberUpdate, db: Session = Depends(get_db)
) -> Member:
    member = get_or_404(db, Member, member_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(member, key, value)
    commit(db)
    db.refresh(member)
    return member