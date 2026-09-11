from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user, require_roles
from app.db.session import get_db
from app.models import District, School, Translation, Menu, Ingredient, UserSchoolAccess
from app.schemas.org import DistrictOut, SchoolOut

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "pmposhan-api"}


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    access_rows = db.scalars(
        select(UserSchoolAccess).where(
            UserSchoolAccess.keycloak_subject == user.subject,
            UserSchoolAccess.active.is_(True),
        )
    ).all()
    return {
        "subject": user.subject,
        "username": user.username,
        "email": user.email,
        "roles": sorted(user.roles),
        "school_access": [
            {
                "school_id": row.school_id,
                "role": row.role,
                "preferred_language": row.preferred_language,
            }
            for row in access_rows
        ],
    }


@router.get("/districts", response_model=list[DistrictOut])
def list_districts(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    return list(
        db.scalars(
            select(District).where(District.active.is_(True)).order_by(District.name_en)
        ).all()
    )


@router.get("/schools", response_model=list[SchoolOut])
def list_schools(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    base = select(School).where(School.active.is_(True))
    if "SYSTEM_ADMIN" not in user.roles and not ({"DISTRICT_OFFICER", "BLOCK_OFFICER", "CLUSTER_OFFICER"} & user.roles):
        school_ids = db.scalars(
            select(UserSchoolAccess.school_id).where(
                UserSchoolAccess.keycloak_subject == user.subject,
                UserSchoolAccess.active.is_(True),
                UserSchoolAccess.school_id.is_not(None),
            )
        ).all()
        if not school_ids:
            return []
        base = base.where(School.id.in_(school_ids))
    return list(db.scalars(base.order_by(School.name_en)).all())


@router.get("/translations")
def translations(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    rows = db.scalars(select(Translation).where(Translation.active.is_(True))).all()
    return [{"key": r.key, "en": r.text_en, "mr": r.text_mr, "category": r.category} for r in rows]


@router.get("/menus")
def menus(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    rows = db.scalars(
        select(Menu).where(Menu.active.is_(True)).order_by(Menu.week_pattern, Menu.day_of_week)
    ).all()
    return [
        {
            "id": r.id,
            "code": r.code,
            "name_en": r.name_en,
            "name_mr": r.name_mr,
            "week_pattern": r.week_pattern,
            "day_of_week": r.day_of_week,
        }
        for r in rows
    ]


@router.get("/ingredients")
def ingredients(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    rows = db.scalars(
        select(Ingredient).where(Ingredient.active.is_(True)).order_by(Ingredient.category, Ingredient.name_en)
    ).all()
    return [
        {
            "id": r.id,
            "code": r.code,
            "name_en": r.name_en,
            "name_mr": r.name_mr,
            "unit": r.base_unit,
            "category": r.category,
        }
        for r in rows
    ]


@router.get("/admin/security-check")
def security_check(
    user: CurrentUser = Depends(require_roles("SYSTEM_ADMIN")),
):
    return {"status": "ok", "message": "SYSTEM_ADMIN access confirmed", "username": user.username}
