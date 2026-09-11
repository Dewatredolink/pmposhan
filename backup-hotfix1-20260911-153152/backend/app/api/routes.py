from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user, require_roles
from app.db.session import get_db
from app.models import (
    DailyAttendance,
    DailyMealEntry,
    District,
    Ingredient,
    Menu,
    School,
    SchoolProfile,
    Translation,
    UserSchoolAccess,
)
from app.schemas.operations import (
    AttendanceInput,
    MealInput,
    SchoolProfileUpsert,
    UserSchoolAccessCreate,
    VerifyInput,
)
from app.schemas.org import DistrictOut, SchoolOut

router = APIRouter()

OFFICER_ROLES = {"SYSTEM_ADMIN", "DISTRICT_OFFICER", "BLOCK_OFFICER", "CLUSTER_OFFICER"}
SCHOOL_ENTRY_ROLES = {"TEACHER", "HEADMASTER", "SYSTEM_ADMIN"}


def _school_access_rows(db: Session, user: CurrentUser):
    return db.scalars(
        select(UserSchoolAccess).where(
            UserSchoolAccess.keycloak_subject == user.subject,
            UserSchoolAccess.active.is_(True),
        )
    ).all()


def _assert_school_access(db: Session, user: CurrentUser, school_id: str, write: bool = False):
    if user.roles & OFFICER_ROLES:
        return
    if write and not (user.roles & SCHOOL_ENTRY_ROLES):
        raise HTTPException(status_code=403, detail="Role cannot edit school operations")
    access = db.scalar(
        select(UserSchoolAccess).where(
            UserSchoolAccess.keycloak_subject == user.subject,
            UserSchoolAccess.school_id == school_id,
            UserSchoolAccess.active.is_(True),
        )
    )
    if not access:
        raise HTTPException(status_code=403, detail="No access to this school")


def _school_or_404(db: Session, school_id: str) -> School:
    school = db.get(School, school_id)
    if not school or not school.active:
        raise HTTPException(status_code=404, detail="School not found")
    return school


def _attendance_dict(row: DailyAttendance | None):
    if not row:
        return None
    return {
        "id": row.id,
        "school_id": row.school_id,
        "meal_date": row.meal_date,
        "class_1_5_enrolled": row.class_1_5_enrolled,
        "class_1_5_present": row.class_1_5_present,
        "class_6_8_enrolled": row.class_6_8_enrolled,
        "class_6_8_present": row.class_6_8_present,
        "total_present": row.class_1_5_present + row.class_6_8_present,
        "status": row.status,
        "entered_by_username": row.entered_by_username,
        "verified_by_username": row.verified_by_username,
        "verified_at": row.verified_at,
    }


def _meal_dict(row: DailyMealEntry | None):
    if not row:
        return None
    return {
        "id": row.id,
        "school_id": row.school_id,
        "meal_date": row.meal_date,
        "menu_id": row.menu_id,
        "menu_code": row.menu.code if row.menu else None,
        "menu_name_en": row.menu.name_en if row.menu else None,
        "menu_name_mr": row.menu.name_mr if row.menu else None,
        "meals_class_1_5": row.meals_class_1_5,
        "meals_class_6_8": row.meals_class_6_8,
        "total_meals": row.total_meals,
        "tasting_done": row.tasting_done,
        "hygiene_ok": row.hygiene_ok,
        "remarks": row.remarks,
        "status": row.status,
        "entered_by_username": row.entered_by_username,
        "verified_by_username": row.verified_by_username,
        "verified_at": row.verified_at,
    }


@router.get("/health")
def health():
    return {"status": "ok", "service": "pmposhan-api", "phase": "2A"}


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    access_rows = _school_access_rows(db, user)
    return {
        "subject": user.subject,
        "username": user.username,
        "email": user.email,
        "roles": sorted(user.roles),
        "school_access": [
            {
                "school_id": row.school_id,
                "school_name_en": row.school.name_en if row.school else None,
                "school_name_mr": row.school.name_mr if row.school else None,
                "role": row.role,
                "preferred_language": row.preferred_language,
            }
            for row in access_rows
        ],
    }


@router.get("/districts", response_model=list[DistrictOut])
def list_districts(db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)):
    return list(db.scalars(select(District).where(District.active.is_(True)).order_by(District.name_en)).all())


@router.get("/schools", response_model=list[SchoolOut])
def list_schools(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    base = select(School).where(School.active.is_(True))
    if not (user.roles & OFFICER_ROLES):
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
def translations(db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)):
    rows = db.scalars(select(Translation).where(Translation.active.is_(True))).all()
    return [{"key": r.key, "en": r.text_en, "mr": r.text_mr, "category": r.category} for r in rows]


@router.get("/menus")
def menus(db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)):
    rows = db.scalars(select(Menu).where(Menu.active.is_(True)).order_by(Menu.day_of_week, Menu.code)).all()
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
def ingredients(db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)):
    rows = db.scalars(select(Ingredient).where(Ingredient.active.is_(True)).order_by(Ingredient.name_en)).all()
    return [
        {
            "id": r.id,
            "code": r.code,
            "name_en": r.name_en,
            "name_mr": r.name_mr,
            "category": r.category,
            "base_unit": r.base_unit,
            "track_inventory": r.track_inventory,
        }
        for r in rows
    ]


@router.get("/school-profiles/{school_id}")
def get_school_profile(
    school_id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    school = _school_or_404(db, school_id)
    _assert_school_access(db, user, school_id)
    profile = db.scalar(select(SchoolProfile).where(SchoolProfile.school_id == school_id))
    assignments = db.scalars(
        select(UserSchoolAccess).where(UserSchoolAccess.school_id == school_id, UserSchoolAccess.active.is_(True))
    ).all()
    return {
        "school": {
            "id": school.id,
            "code": school.code,
            "udise_code": school.udise_code,
            "name_en": school.name_en,
            "name_mr": school.name_mr,
            "village": school.village,
            "class_1_5_strength": school.class_1_5_strength,
            "class_6_8_strength": school.class_6_8_strength,
        },
        "profile": {
            "kitchen_type": profile.kitchen_type,
            "cooking_agency": profile.cooking_agency,
            "headmaster_name": profile.headmaster_name,
            "meal_incharge_name": profile.meal_incharge_name,
            "contact_mobile": profile.contact_mobile,
        } if profile else None,
        "assignments": [
            {"id": a.id, "username": a.username, "role": a.role, "preferred_language": a.preferred_language}
            for a in assignments
        ],
    }


@router.put("/school-profiles/{school_id}")
def upsert_school_profile(
    school_id: str,
    payload: SchoolProfileUpsert,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _school_or_404(db, school_id)
    _assert_school_access(db, user, school_id, write=True)
    if not (user.roles & {"HEADMASTER", "SYSTEM_ADMIN"}):
        raise HTTPException(status_code=403, detail="Headmaster or System Admin role required")
    row = db.scalar(select(SchoolProfile).where(SchoolProfile.school_id == school_id))
    if not row:
        row = SchoolProfile(school_id=school_id, created_by=user.username)
        db.add(row)
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id}


@router.get("/user-school-access")
def list_user_school_access(
    school_id: str | None = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_roles("SYSTEM_ADMIN")),
):
    q = select(UserSchoolAccess).where(UserSchoolAccess.active.is_(True))
    if school_id:
        q = q.where(UserSchoolAccess.school_id == school_id)
    rows = db.scalars(q.order_by(UserSchoolAccess.username)).all()
    return [
        {"id": r.id, "keycloak_subject": r.keycloak_subject, "username": r.username, "school_id": r.school_id, "role": r.role, "preferred_language": r.preferred_language}
        for r in rows
    ]


@router.post("/user-school-access")
def create_user_school_access(
    payload: UserSchoolAccessCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("SYSTEM_ADMIN")),
):
    _school_or_404(db, payload.school_id)
    if payload.role not in {"TEACHER", "HEADMASTER", "CLUSTER_OFFICER", "BLOCK_OFFICER", "DISTRICT_OFFICER", "SYSTEM_ADMIN"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    if payload.preferred_language not in {"mr", "en"}:
        raise HTTPException(status_code=400, detail="Preferred language must be mr or en")
    exists = db.scalar(
        select(UserSchoolAccess).where(
            UserSchoolAccess.keycloak_subject == payload.keycloak_subject,
            UserSchoolAccess.school_id == payload.school_id,
            UserSchoolAccess.role == payload.role,
        )
    )
    if exists:
        exists.active = True
        exists.username = payload.username
        exists.preferred_language = payload.preferred_language
        db.commit()
        return {"ok": True, "id": exists.id, "reactivated": True}
    row = UserSchoolAccess(**payload.model_dump(), active=True, created_by=user.username)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id}


@router.get("/daily-operations")
def get_daily_operations(
    school_id: str,
    meal_date: date,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    school = _school_or_404(db, school_id)
    _assert_school_access(db, user, school_id)
    attendance = db.scalar(
        select(DailyAttendance).where(DailyAttendance.school_id == school_id, DailyAttendance.meal_date == meal_date)
    )
    meal = db.scalar(
        select(DailyMealEntry).where(DailyMealEntry.school_id == school_id, DailyMealEntry.meal_date == meal_date)
    )
    return {
        "school": {"id": school.id, "name_en": school.name_en, "name_mr": school.name_mr},
        "attendance": _attendance_dict(attendance),
        "meal": _meal_dict(meal),
    }


@router.put("/daily-attendance")
def save_daily_attendance(
    payload: AttendanceInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _school_or_404(db, payload.school_id)
    _assert_school_access(db, user, payload.school_id, write=True)
    row = db.scalar(
        select(DailyAttendance).where(
            DailyAttendance.school_id == payload.school_id,
            DailyAttendance.meal_date == payload.meal_date,
        )
    )
    if row and row.status == "VERIFIED":
        raise HTTPException(status_code=409, detail="Verified attendance cannot be edited")
    if not row:
        row = DailyAttendance(
            school_id=payload.school_id,
            meal_date=payload.meal_date,
            entered_by_subject=user.subject,
            entered_by_username=user.username,
            created_by=user.username,
        )
        db.add(row)
    row.class_1_5_enrolled = payload.class_1_5_enrolled
    row.class_1_5_present = payload.class_1_5_present
    row.class_6_8_enrolled = payload.class_6_8_enrolled
    row.class_6_8_present = payload.class_6_8_present
    row.status = payload.status
    row.entered_by_subject = user.subject
    row.entered_by_username = user.username
    db.commit()
    db.refresh(row)
    return _attendance_dict(row)


@router.put("/daily-meal")
def save_daily_meal(
    payload: MealInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _school_or_404(db, payload.school_id)
    _assert_school_access(db, user, payload.school_id, write=True)
    menu = db.get(Menu, payload.menu_id)
    if not menu or not menu.active:
        raise HTTPException(status_code=404, detail="Menu not found")
    attendance = db.scalar(
        select(DailyAttendance).where(
            DailyAttendance.school_id == payload.school_id,
            DailyAttendance.meal_date == payload.meal_date,
        )
    )
    if payload.meals_class_1_5 + payload.meals_class_6_8 > 0 and attendance:
        if payload.meals_class_1_5 > attendance.class_1_5_present or payload.meals_class_6_8 > attendance.class_6_8_present:
            raise HTTPException(status_code=400, detail="Meals served cannot exceed present students")
    row = db.scalar(
        select(DailyMealEntry).where(
            DailyMealEntry.school_id == payload.school_id,
            DailyMealEntry.meal_date == payload.meal_date,
        )
    )
    if row and row.status == "VERIFIED":
        raise HTTPException(status_code=409, detail="Verified meal entry cannot be edited")
    if not row:
        row = DailyMealEntry(
            school_id=payload.school_id,
            meal_date=payload.meal_date,
            menu_id=payload.menu_id,
            entered_by_subject=user.subject,
            entered_by_username=user.username,
            created_by=user.username,
        )
        db.add(row)
    row.menu_id = payload.menu_id
    row.meals_class_1_5 = payload.meals_class_1_5
    row.meals_class_6_8 = payload.meals_class_6_8
    row.total_meals = payload.meals_class_1_5 + payload.meals_class_6_8
    row.tasting_done = payload.tasting_done
    row.hygiene_ok = payload.hygiene_ok
    row.remarks = payload.remarks
    row.status = payload.status
    row.entered_by_subject = user.subject
    row.entered_by_username = user.username
    db.commit()
    db.refresh(row)
    return _meal_dict(row)


@router.post("/daily-operations/verify")
def verify_daily_operations(
    payload: VerifyInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("HEADMASTER", "SYSTEM_ADMIN")),
):
    _school_or_404(db, payload.school_id)
    _assert_school_access(db, user, payload.school_id)
    attendance = db.scalar(
        select(DailyAttendance).where(DailyAttendance.school_id == payload.school_id, DailyAttendance.meal_date == payload.meal_date)
    )
    meal = db.scalar(
        select(DailyMealEntry).where(DailyMealEntry.school_id == payload.school_id, DailyMealEntry.meal_date == payload.meal_date)
    )
    if not attendance or not meal:
        raise HTTPException(status_code=400, detail="Attendance and meal entry are both required")
    if attendance.status != "SUBMITTED" or meal.status != "SUBMITTED":
        raise HTTPException(status_code=400, detail="Both records must be submitted before verification")
    if not meal.tasting_done or not meal.hygiene_ok:
        raise HTTPException(status_code=400, detail="Tasting and hygiene checks must be complete")
    now = datetime.now(timezone.utc)
    for row in (attendance, meal):
        row.status = "VERIFIED"
        row.verified_by_subject = user.subject
        row.verified_by_username = user.username
        row.verified_at = now
    db.commit()
    return {"ok": True, "status": "VERIFIED", "verified_by": user.username, "verified_at": now}


@router.get("/dashboard-summary")
def dashboard_summary(
    school_id: str,
    meal_date: date | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    school = _school_or_404(db, school_id)
    _assert_school_access(db, user, school_id)
    target = meal_date or date.today()
    attendance = db.scalar(select(DailyAttendance).where(DailyAttendance.school_id == school_id, DailyAttendance.meal_date == target))
    meal = db.scalar(select(DailyMealEntry).where(DailyMealEntry.school_id == school_id, DailyMealEntry.meal_date == target))
    month_start = target.replace(day=1)
    month_meals = db.scalar(
        select(func.coalesce(func.sum(DailyMealEntry.total_meals), 0)).where(
            DailyMealEntry.school_id == school_id,
            DailyMealEntry.meal_date >= month_start,
            DailyMealEntry.meal_date <= target,
        )
    ) or 0
    return {
        "school_id": school.id,
        "students": school.class_1_5_strength + school.class_6_8_strength,
        "present_today": (attendance.class_1_5_present + attendance.class_6_8_present) if attendance else 0,
        "meals_today": meal.total_meals if meal else 0,
        "meals_month": int(month_meals),
        "attendance_status": attendance.status if attendance else "NOT_ENTERED",
        "meal_status": meal.status if meal else "NOT_ENTERED",
    }


@router.get("/admin/security-check")
def security_check(_: CurrentUser = Depends(require_roles("SYSTEM_ADMIN"))):
    return {"ok": True, "message": "SYSTEM_ADMIN access confirmed"}
