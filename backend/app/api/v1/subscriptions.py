from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.auth import Identity, ensure_scope, require_role
from app.api.v1.common import commit, get_db, get_or_404
from app.audit import record_audit
from app.models import Member, MemberSubscription
from app.schemas import SubscriptionPatch, SubscriptionRead, SubscriptionUpdate

router = APIRouter()


def public_subscription(subscription: MemberSubscription) -> dict:
    return {
        "apim_subscription_id": subscription.apim_subscription_id,
        "subscription_display_name": subscription.subscription_display_name,
        "status": subscription.status,
        "last_rotated_at": subscription.last_rotated_at,
    }


@router.get("/members/{member_id}/subscription", response_model=SubscriptionRead)
def get_subscription(
    member_id: int,
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
) -> dict:
    ensure_scope(identity, db, member_id=member_id)
    get_or_404(db, Member, member_id)
    subscription = (
        db.query(MemberSubscription)
        .filter(MemberSubscription.member_id == member_id)
        .order_by(MemberSubscription.id)
        .first()
    )
    if subscription is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": "Subscription was not found.",
                "field_errors": [],
            },
        )
    return public_subscription(subscription)


@router.put("/members/{member_id}/subscription", response_model=SubscriptionRead)
def put_subscription(
    member_id: int,
    payload: SubscriptionUpdate,
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
) -> dict:
    ensure_scope(identity, db, member_id=member_id)
    get_or_404(db, Member, member_id)
    subscription = (
        db.query(MemberSubscription)
        .filter(MemberSubscription.member_id == member_id)
        .order_by(MemberSubscription.id)
        .first()
    )
    values = payload.model_dump()
    if subscription is None:
        subscription = MemberSubscription(member_id=member_id, **values)
        db.add(subscription)
    else:
        for key, value in values.items():
            setattr(subscription, key, value)
    commit(db)
    db.refresh(subscription)
    record_audit(
        db, identity, action="upsert", entity_type="member_subscription", entity_id=subscription.id
    )
    return public_subscription(subscription)


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionRead)
def patch_subscription(
    subscription_id: int,
    payload: SubscriptionPatch,
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
) -> dict:
    subscription = get_or_404(db, MemberSubscription, subscription_id)
    ensure_scope(identity, db, member_id=subscription.member_id)
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(subscription, key, value)
    commit(db)
    db.refresh(subscription)
    record_audit(
        db, identity, action="update", entity_type="member_subscription", entity_id=subscription.id
    )
    return public_subscription(subscription)


@router.delete("/subscriptions/{subscription_id}", status_code=204)
def delete_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
) -> None:
    subscription = get_or_404(db, MemberSubscription, subscription_id)
    ensure_scope(identity, db, member_id=subscription.member_id)
    db.delete(subscription)
    commit(db)
    record_audit(
        db, identity, action="delete", entity_type="member_subscription", entity_id=subscription_id
    )
