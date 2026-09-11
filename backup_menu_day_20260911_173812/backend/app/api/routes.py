from datetime import date, datetime, timezone
from calendar import monthrange
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user, require_roles
from app.db.session import get_db
from app.models import (
    DailyAttendance,
    DailyMealEntry,
    District,
    Block,
    Cluster,
    Ingredient,
    Menu,
    Recipe,
    School,
    SchoolProfile,
    Translation,
    UserSchoolAccess,
    UserOrgAccess,
    MonthlySchoolReturn,
    MonthlyReturnAction,
    StockReceipt,
    StockReceiptLine,
    StockTransaction,
    StockAdjustment,
    PhysicalStockVerification,
    PhysicalStockVerificationLine,
    SchoolCalendarDay,
)
from app.schemas.operations import (
    AttendanceInput,
    MealInput,
    SchoolProfileUpsert,
    UserSchoolAccessCreate,
    VerifyInput,
)
from app.schemas.org import DistrictOut, SchoolOut
from app.schemas.inventory import (
    StockOpeningInput, StockReceiptInput, StockAdjustmentInput, PhysicalStockVerificationInput,
)
from app.schemas.monthly import MonthlyGenerateInput, MonthlyActionInput, OrgAccessInput

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


def _accessible_school_ids(db: Session, user: CurrentUser) -> list[str]:
    if "SYSTEM_ADMIN" in user.roles:
        return list(db.scalars(select(School.id).where(School.active.is_(True))).all())

    ids: set[str] = set()
    school_ids = db.scalars(
        select(UserSchoolAccess.school_id).where(
            UserSchoolAccess.keycloak_subject == user.subject,
            UserSchoolAccess.active.is_(True),
            UserSchoolAccess.school_id.is_not(None),
        )
    ).all()
    ids.update(str(x) for x in school_ids if x)

    org_rows = db.scalars(
        select(UserOrgAccess).where(
            UserOrgAccess.keycloak_subject == user.subject,
            UserOrgAccess.active.is_(True),
        )
    ).all()
    for row in org_rows:
        q = select(School.id).join(Cluster, School.cluster_id == Cluster.id).join(Block, Cluster.block_id == Block.id).where(School.active.is_(True))
        if row.cluster_id:
            q = q.where(School.cluster_id == row.cluster_id)
        elif row.block_id:
            q = q.where(Cluster.block_id == row.block_id)
        elif row.district_id:
            q = q.where(Block.district_id == row.district_id)
        else:
            continue
        ids.update(str(x) for x in db.scalars(q).all())
    return sorted(ids)


def _assert_school_access(db: Session, user: CurrentUser, school_id: str, write: bool = False):
    if write and not (user.roles & SCHOOL_ENTRY_ROLES):
        raise HTTPException(status_code=403, detail="Role cannot edit school operations")
    if school_id not in _accessible_school_ids(db, user):
        raise HTTPException(status_code=403, detail="No access to this school")


def _school_or_404(db: Session, school_id: str) -> School:
    school = db.get(School, school_id)
    if not school or not school.active:
        raise HTTPException(status_code=404, detail="School not found")
    return school



def _stock_balance(db: Session, school_id: str, ingredient_id: str) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(StockTransaction.quantity), 0)).where(
            StockTransaction.school_id == school_id,
            StockTransaction.ingredient_id == ingredient_id,
        )
    )
    return Decimal(str(value or 0))


def _recipe_consumption(db: Session, meal: DailyMealEntry):
    rows = db.scalars(
        select(Recipe).where(
            Recipe.menu_id == meal.menu_id,
            Recipe.active.is_(True),
            Recipe.effective_from <= meal.meal_date,
            (Recipe.effective_to.is_(None) | (Recipe.effective_to >= meal.meal_date)),
        )
    ).all()
    consumption: dict[str, Decimal] = {}
    for r in rows:
        qty = Decimal("0")
        per_student = Decimal(str(r.qty_per_student))
        if r.student_group == "CLASS_1_5":
            qty = per_student * meal.meals_class_1_5
        elif r.student_group == "CLASS_6_8":
            qty = per_student * meal.meals_class_6_8
        elif r.student_group == "ALL":
            qty = per_student * meal.total_meals
        if qty > 0:
            consumption[r.ingredient_id] = consumption.get(r.ingredient_id, Decimal("0")) + qty
    return consumption


def _post_verified_meal_consumption(db: Session, meal: DailyMealEntry, user: CurrentUser):
    existing = db.scalars(
        select(StockTransaction).where(
            StockTransaction.school_id == meal.school_id,
            StockTransaction.reference_type == "DAILY_MEAL",
            StockTransaction.reference_id == meal.id,
            StockTransaction.transaction_type == "CONSUMPTION",
        )
    ).all()
    if existing:
        return existing

    consumption = _recipe_consumption(db, meal)
    if not consumption:
        raise HTTPException(status_code=400, detail="No active recipe is configured for the selected menu/date")

    shortages = []
    for ingredient_id, required in consumption.items():
        ingredient = db.get(Ingredient, ingredient_id)
        if not ingredient or not ingredient.track_inventory:
            continue
        available = _stock_balance(db, meal.school_id, ingredient_id)
        if available < required:
            shortages.append((ingredient, required, available))
    if shortages:
        detail = "; ".join(
            f"{ingredient.name_en}: required {required} {ingredient.base_unit}, available {available} {ingredient.base_unit}"
            for ingredient, required, available in shortages
        )
        raise HTTPException(status_code=409, detail=f"Insufficient stock - {detail}")

    posted = []
    for ingredient_id, required in consumption.items():
        ingredient = db.get(Ingredient, ingredient_id)
        if not ingredient or not ingredient.track_inventory:
            continue
        row = StockTransaction(
            school_id=meal.school_id,
            ingredient_id=ingredient_id,
            transaction_date=meal.meal_date,
            transaction_type="CONSUMPTION",
            quantity=-required,
            reference_type="DAILY_MEAL",
            reference_id=meal.id,
            reference_no=f"MEAL-{meal.meal_date.isoformat()}",
            remarks=f"Auto consumption for {meal.total_meals} verified meals",
            entered_by_subject=user.subject,
            entered_by_username=user.username,
            created_by=user.username,
        )
        db.add(row)
        posted.append(row)
    db.flush()
    return posted


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
    return {"status": "ok", "service": "pmposhan-api", "phase": "3C"}


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
    school_ids = _accessible_school_ids(db, user)
    if not school_ids:
        return []
    base = select(School).where(School.active.is_(True), School.id.in_(school_ids))
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
    if payload.status == "SUBMITTED" and (not payload.tasting_done or not payload.hygiene_ok):
        raise HTTPException(status_code=400, detail="Complete both meal tasting and hygiene checks before submitting")
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
    posted = _post_verified_meal_consumption(db, meal, user)
    for row in (attendance, meal):
        row.status = "VERIFIED"
        row.verified_by_subject = user.subject
        row.verified_by_username = user.username
        row.verified_at = now
    db.commit()
    return {
        "ok": True,
        "status": "VERIFIED",
        "verified_by": user.username,
        "verified_at": now,
        "stock_consumption_transactions": len(posted),
    }


@router.post("/stock/opening-balance")
def create_opening_balance(
    payload: StockOpeningInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _school_or_404(db, payload.school_id)
    _assert_school_access(db, user, payload.school_id, write=True)
    if not (user.roles & {"HEADMASTER", "SYSTEM_ADMIN"}):
        raise HTTPException(status_code=403, detail="Headmaster or System Admin role required for opening balance")
    ing = db.get(Ingredient, payload.ingredient_id)
    if not ing or not ing.active or not ing.track_inventory:
        raise HTTPException(status_code=400, detail="Invalid inventory ingredient")
    existing_count = db.scalar(select(func.count(StockTransaction.id)).where(
        StockTransaction.school_id == payload.school_id, StockTransaction.ingredient_id == payload.ingredient_id
    )) or 0
    if existing_count:
        raise HTTPException(status_code=409, detail="Opening balance is allowed only before any transaction exists for this ingredient")
    row = StockTransaction(
        school_id=payload.school_id, ingredient_id=payload.ingredient_id, transaction_date=payload.opening_date,
        transaction_type="OPENING", quantity=payload.quantity, reference_type="OPENING_BALANCE",
        reference_id=f"{payload.school_id}:{payload.ingredient_id}", reference_no="OPENING", remarks=payload.remarks,
        entered_by_subject=user.subject, entered_by_username=user.username, created_by=user.username,
    )
    db.add(row); db.commit(); db.refresh(row)
    return {"ok": True, "id": row.id, "quantity": float(row.quantity), "unit": ing.base_unit}


@router.get("/stock/balances")
def stock_balances(
    school_id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _school_or_404(db, school_id)
    _assert_school_access(db, user, school_id)
    ingredients = db.scalars(
        select(Ingredient).where(Ingredient.active.is_(True), Ingredient.track_inventory.is_(True)).order_by(Ingredient.name_en)
    ).all()
    totals = dict(db.execute(
        select(StockTransaction.ingredient_id, func.coalesce(func.sum(StockTransaction.quantity), 0))
        .where(StockTransaction.school_id == school_id)
        .group_by(StockTransaction.ingredient_id)
    ).all())
    result = []
    for ing in ingredients:
        balance = Decimal(str(totals.get(ing.id, 0) or 0))
        reorder = Decimal(str(ing.reorder_level or 0))
        result.append({
            "ingredient_id": ing.id, "code": ing.code, "name_en": ing.name_en, "name_mr": ing.name_mr,
            "unit": ing.base_unit, "balance": float(balance), "reorder_level": float(reorder),
            "low_stock": balance <= reorder if reorder > 0 else False,
        })
    return result


@router.get("/stock/ledger")
def stock_ledger(
    school_id: str,
    ingredient_id: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _school_or_404(db, school_id)
    _assert_school_access(db, user, school_id)
    q = select(StockTransaction).where(StockTransaction.school_id == school_id)
    if ingredient_id:
        q = q.where(StockTransaction.ingredient_id == ingredient_id)
    if from_date:
        q = q.where(StockTransaction.transaction_date >= from_date)
    if to_date:
        q = q.where(StockTransaction.transaction_date <= to_date)
    rows = db.scalars(q.order_by(StockTransaction.transaction_date.desc(), StockTransaction.created_at.desc())).all()
    return [{
        "id": r.id, "transaction_date": r.transaction_date, "transaction_type": r.transaction_type,
        "ingredient_id": r.ingredient_id, "ingredient_code": r.ingredient.code if r.ingredient else None,
        "ingredient_name_en": r.ingredient.name_en if r.ingredient else None,
        "ingredient_name_mr": r.ingredient.name_mr if r.ingredient else None,
        "unit": r.ingredient.base_unit if r.ingredient else None, "quantity": float(r.quantity),
        "reference_type": r.reference_type, "reference_no": r.reference_no, "remarks": r.remarks,
        "entered_by_username": r.entered_by_username,
    } for r in rows]


@router.get("/stock/receipts")
def stock_receipts(
    school_id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _school_or_404(db, school_id)
    _assert_school_access(db, user, school_id)
    rows = db.scalars(
        select(StockReceipt).where(StockReceipt.school_id == school_id).order_by(StockReceipt.receipt_date.desc(), StockReceipt.created_at.desc())
    ).all()
    return [{
        "id": r.id, "receipt_date": r.receipt_date, "receipt_no": r.receipt_no, "source_name": r.source_name,
        "remarks": r.remarks, "entered_by_username": r.entered_by_username,
        "lines": [{
            "ingredient_id": ln.ingredient_id, "ingredient_name_en": ln.ingredient.name_en if ln.ingredient else None,
            "ingredient_name_mr": ln.ingredient.name_mr if ln.ingredient else None, "unit": ln.ingredient.base_unit if ln.ingredient else None,
            "quantity": float(ln.quantity), "unit_cost": float(ln.unit_cost) if ln.unit_cost is not None else None,
        } for ln in r.lines]
    } for r in rows]


@router.post("/stock/receipts")
def create_stock_receipt(
    payload: StockReceiptInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _school_or_404(db, payload.school_id)
    _assert_school_access(db, user, payload.school_id, write=True)
    if not (user.roles & {"TEACHER", "HEADMASTER", "SYSTEM_ADMIN"}):
        raise HTTPException(status_code=403, detail="Teacher, Headmaster or System Admin role required")
    duplicate = db.scalar(select(StockReceipt).where(
        StockReceipt.school_id == payload.school_id, StockReceipt.receipt_no == payload.receipt_no
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail="Receipt number already exists for this school")
    for line in payload.lines:
        ing = db.get(Ingredient, line.ingredient_id)
        if not ing or not ing.active or not ing.track_inventory:
            raise HTTPException(status_code=400, detail=f"Invalid inventory ingredient: {line.ingredient_id}")
    receipt = StockReceipt(
        school_id=payload.school_id, receipt_date=payload.receipt_date, receipt_no=payload.receipt_no,
        source_name=payload.source_name, remarks=payload.remarks, entered_by_subject=user.subject,
        entered_by_username=user.username, created_by=user.username,
    )
    db.add(receipt)
    db.flush()
    for line in payload.lines:
        db.add(StockReceiptLine(
            receipt_id=receipt.id, ingredient_id=line.ingredient_id, quantity=line.quantity, unit_cost=line.unit_cost,
            created_by=user.username,
        ))
        db.add(StockTransaction(
            school_id=payload.school_id, ingredient_id=line.ingredient_id, transaction_date=payload.receipt_date,
            transaction_type="RECEIPT", quantity=line.quantity, reference_type="STOCK_RECEIPT", reference_id=receipt.id,
            reference_no=payload.receipt_no, remarks=payload.remarks or payload.source_name,
            entered_by_subject=user.subject, entered_by_username=user.username, created_by=user.username,
        ))
    db.commit()
    return {"ok": True, "id": receipt.id, "receipt_no": receipt.receipt_no, "lines": len(payload.lines)}


@router.post("/stock/adjustments")
def create_stock_adjustment(
    payload: StockAdjustmentInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("HEADMASTER", "SYSTEM_ADMIN")),
):
    _school_or_404(db, payload.school_id)
    _assert_school_access(db, user, payload.school_id)
    ing = db.get(Ingredient, payload.ingredient_id)
    if not ing or not ing.active or not ing.track_inventory:
        raise HTTPException(status_code=400, detail="Invalid inventory ingredient")
    duplicate = db.scalar(select(StockAdjustment).where(
        StockAdjustment.school_id == payload.school_id,
        StockAdjustment.adjustment_no == payload.adjustment_no,
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail="Adjustment number already exists for this school")
    if payload.quantity < 0:
        available = _stock_balance(db, payload.school_id, payload.ingredient_id)
        if available + payload.quantity < 0:
            raise HTTPException(
                status_code=409,
                detail=f"Adjustment would create negative stock. Available {available} {ing.base_unit}",
            )
    row = StockAdjustment(
        school_id=payload.school_id,
        adjustment_date=payload.adjustment_date,
        adjustment_no=payload.adjustment_no,
        ingredient_id=payload.ingredient_id,
        quantity=payload.quantity,
        reason_code=payload.reason_code,
        remarks=payload.remarks,
        entered_by_subject=user.subject,
        entered_by_username=user.username,
        created_by=user.username,
    )
    db.add(row)
    db.flush()
    tx = StockTransaction(
        school_id=payload.school_id,
        ingredient_id=payload.ingredient_id,
        transaction_date=payload.adjustment_date,
        transaction_type="ADJUSTMENT",
        quantity=payload.quantity,
        reference_type="STOCK_ADJUSTMENT",
        reference_id=row.id,
        reference_no=payload.adjustment_no,
        remarks=f"{payload.reason_code}: {payload.remarks or ''}".strip(),
        entered_by_subject=user.subject,
        entered_by_username=user.username,
        created_by=user.username,
    )
    db.add(tx)
    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "id": row.id,
        "adjustment_no": row.adjustment_no,
        "quantity": float(row.quantity),
        "balance_after": float(_stock_balance(db, payload.school_id, payload.ingredient_id)),
    }


@router.get("/stock/adjustments")
def list_stock_adjustments(
    school_id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _school_or_404(db, school_id)
    _assert_school_access(db, user, school_id)
    rows = db.scalars(
        select(StockAdjustment)
        .where(StockAdjustment.school_id == school_id)
        .order_by(StockAdjustment.adjustment_date.desc(), StockAdjustment.created_at.desc())
    ).all()
    return [{
        "id": r.id,
        "adjustment_date": r.adjustment_date,
        "adjustment_no": r.adjustment_no,
        "ingredient_id": r.ingredient_id,
        "ingredient_name_en": r.ingredient.name_en if r.ingredient else None,
        "ingredient_name_mr": r.ingredient.name_mr if r.ingredient else None,
        "unit": r.ingredient.base_unit if r.ingredient else None,
        "quantity": float(r.quantity),
        "reason_code": r.reason_code,
        "remarks": r.remarks,
        "entered_by_username": r.entered_by_username,
    } for r in rows]


@router.post("/stock/physical-verifications")
def create_physical_stock_verification(
    payload: PhysicalStockVerificationInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("HEADMASTER", "SYSTEM_ADMIN")),
):
    _school_or_404(db, payload.school_id)
    _assert_school_access(db, user, payload.school_id)
    duplicate = db.scalar(select(PhysicalStockVerification).where(
        PhysicalStockVerification.school_id == payload.school_id,
        PhysicalStockVerification.verification_no == payload.verification_no,
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail="Verification number already exists for this school")

    header = PhysicalStockVerification(
        school_id=payload.school_id,
        verification_date=payload.verification_date,
        verification_no=payload.verification_no,
        remarks=payload.remarks,
        entered_by_subject=user.subject,
        entered_by_username=user.username,
        created_by=user.username,
    )
    db.add(header)
    db.flush()
    variance_count = 0
    for line in payload.lines:
        ing = db.get(Ingredient, line.ingredient_id)
        if not ing or not ing.active or not ing.track_inventory:
            raise HTTPException(status_code=400, detail=f"Invalid inventory ingredient: {line.ingredient_id}")
        system_qty = _stock_balance(db, payload.school_id, line.ingredient_id)
        variance = line.physical_quantity - system_qty
        db.add(PhysicalStockVerificationLine(
            verification_id=header.id,
            ingredient_id=line.ingredient_id,
            system_quantity=system_qty,
            physical_quantity=line.physical_quantity,
            variance_quantity=variance,
            created_by=user.username,
        ))
        if variance != 0:
            variance_count += 1
            db.add(StockTransaction(
                school_id=payload.school_id,
                ingredient_id=line.ingredient_id,
                transaction_date=payload.verification_date,
                transaction_type="PHYSICAL_ADJUSTMENT",
                quantity=variance,
                reference_type="PHYSICAL_STOCK",
                reference_id=header.id,
                reference_no=payload.verification_no,
                remarks=payload.remarks or "Physical stock verification variance",
                entered_by_subject=user.subject,
                entered_by_username=user.username,
                created_by=user.username,
            ))
    db.commit()
    return {"ok": True, "id": header.id, "verification_no": header.verification_no, "variance_lines": variance_count}


@router.get("/stock/physical-verifications")
def list_physical_stock_verifications(
    school_id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _school_or_404(db, school_id)
    _assert_school_access(db, user, school_id)
    rows = db.scalars(
        select(PhysicalStockVerification)
        .where(PhysicalStockVerification.school_id == school_id)
        .order_by(PhysicalStockVerification.verification_date.desc(), PhysicalStockVerification.created_at.desc())
    ).all()
    return [{
        "id": r.id,
        "verification_date": r.verification_date,
        "verification_no": r.verification_no,
        "remarks": r.remarks,
        "entered_by_username": r.entered_by_username,
        "lines": [{
            "ingredient_id": ln.ingredient_id,
            "ingredient_name_en": ln.ingredient.name_en if ln.ingredient else None,
            "ingredient_name_mr": ln.ingredient.name_mr if ln.ingredient else None,
            "unit": ln.ingredient.base_unit if ln.ingredient else None,
            "system_quantity": float(ln.system_quantity),
            "physical_quantity": float(ln.physical_quantity),
            "variance_quantity": float(ln.variance_quantity),
        } for ln in r.lines],
    } for r in rows]


@router.get("/stock/monthly-summary")
def stock_monthly_summary(
    school_id: str,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _school_or_404(db, school_id)
    _assert_school_access(db, user, school_id)
    if month < 1 or month > 12 or year < 2000 or year > 2200:
        raise HTTPException(status_code=400, detail="Invalid year/month")
    from calendar import monthrange
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    ingredients = db.scalars(
        select(Ingredient).where(Ingredient.active.is_(True), Ingredient.track_inventory.is_(True)).order_by(Ingredient.name_en)
    ).all()
    result = []
    for ing in ingredients:
        opening = Decimal(str(db.scalar(select(func.coalesce(func.sum(StockTransaction.quantity), 0)).where(
            StockTransaction.school_id == school_id,
            StockTransaction.ingredient_id == ing.id,
            StockTransaction.transaction_date < first,
        )) or 0))
        period_rows = db.execute(select(
            StockTransaction.transaction_type,
            func.coalesce(func.sum(StockTransaction.quantity), 0),
        ).where(
            StockTransaction.school_id == school_id,
            StockTransaction.ingredient_id == ing.id,
            StockTransaction.transaction_date >= first,
            StockTransaction.transaction_date <= last,
        ).group_by(StockTransaction.transaction_type)).all()
        by_type = {k: Decimal(str(v or 0)) for k, v in period_rows}
        receipts = by_type.get("RECEIPT", Decimal("0"))
        consumption = by_type.get("CONSUMPTION", Decimal("0"))
        adjustments = by_type.get("ADJUSTMENT", Decimal("0")) + by_type.get("PHYSICAL_ADJUSTMENT", Decimal("0"))
        opening_in_period = by_type.get("OPENING", Decimal("0"))
        closing = opening + sum(by_type.values(), Decimal("0"))
        result.append({
            "ingredient_id": ing.id,
            "code": ing.code,
            "name_en": ing.name_en,
            "name_mr": ing.name_mr,
            "unit": ing.base_unit,
            "opening": float(opening + opening_in_period),
            "receipts": float(receipts),
            "consumption": float(abs(consumption)),
            "adjustments": float(adjustments),
            "closing": float(closing),
            "reorder_level": float(Decimal(str(ing.reorder_level or 0))),
            "low_stock": closing <= Decimal(str(ing.reorder_level or 0)) if Decimal(str(ing.reorder_level or 0)) > 0 else False,
        })
    return {
        "school_id": school_id,
        "year": year,
        "month": month,
        "from_date": first,
        "to_date": last,
        "items": result,
    }


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


def _role_for_action(user: CurrentUser) -> str:
    for role in ("SYSTEM_ADMIN", "DISTRICT_OFFICER", "BLOCK_OFFICER", "CLUSTER_OFFICER", "HEADMASTER", "TEACHER"):
        if role in user.roles:
            return role
    return "USER"


def _return_dict(row: MonthlySchoolReturn):
    school = row.school
    cluster = school.cluster if school else None
    block = cluster.block if cluster else None
    district = block.district if block else None
    actions = sorted(row.actions or [], key=lambda x: x.acted_at)
    return {
        "id": row.id,
        "school_id": row.school_id,
        "school_code": school.code if school else None,
        "udise_code": school.udise_code if school else None,
        "school_name_en": school.name_en if school else None,
        "school_name_mr": school.name_mr if school else None,
        "cluster_name_en": cluster.name_en if cluster else None,
        "cluster_name_mr": cluster.name_mr if cluster else None,
        "block_name_en": block.name_en if block else None,
        "block_name_mr": block.name_mr if block else None,
        "district_name_en": district.name_en if district else None,
        "district_name_mr": district.name_mr if district else None,
        "year": row.year,
        "month": row.month,
        "recorded_days": row.recorded_days,
        "verified_days": row.verified_days,
        "incomplete_days": row.incomplete_days,
        "attendance_class_1_5": row.attendance_class_1_5,
        "attendance_class_6_8": row.attendance_class_6_8,
        "meals_class_1_5": row.meals_class_1_5,
        "meals_class_6_8": row.meals_class_6_8,
        "total_meals": row.total_meals,
        "tasting_exception_days": row.tasting_exception_days,
        "hygiene_exception_days": row.hygiene_exception_days,
        "status": row.status,
        "generated_by_username": row.generated_by_username,
        "generated_at": row.generated_at,
        "submitted_by_username": row.submitted_by_username,
        "submitted_at": row.submitted_at,
        "cluster_reviewed_by": row.cluster_reviewed_by,
        "cluster_reviewed_at": row.cluster_reviewed_at,
        "block_approved_by": row.block_approved_by,
        "block_approved_at": row.block_approved_at,
        "return_reason": row.return_reason,
        "actions": [
            {
                "action": a.action,
                "from_status": a.from_status,
                "to_status": a.to_status,
                "actor_username": a.actor_username,
                "actor_role": a.actor_role,
                "remarks": a.remarks,
                "acted_at": a.acted_at,
            }
            for a in actions
        ],
    }


def _append_return_action(db: Session, row: MonthlySchoolReturn, user: CurrentUser, action: str, from_status: str | None, to_status: str, remarks: str | None = None):
    db.add(MonthlyReturnAction(
        monthly_return_id=row.id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        actor_subject=user.subject,
        actor_username=user.username,
        actor_role=_role_for_action(user),
        remarks=remarks,
        acted_at=datetime.now(timezone.utc),
        created_by=user.username,
    ))


def _monthly_metrics(db: Session, school_id: str, year: int, month: int):
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    attendance_rows = db.scalars(
        select(DailyAttendance).where(
            DailyAttendance.school_id == school_id,
            DailyAttendance.meal_date >= first,
            DailyAttendance.meal_date <= last,
        )
    ).all()
    meal_rows = db.scalars(
        select(DailyMealEntry).where(
            DailyMealEntry.school_id == school_id,
            DailyMealEntry.meal_date >= first,
            DailyMealEntry.meal_date <= last,
        )
    ).all()
    attendance_by_date = {r.meal_date: r for r in attendance_rows}
    meal_by_date = {r.meal_date: r for r in meal_rows}
    recorded_dates = set(attendance_by_date) | set(meal_by_date)
    calendar_rows = db.scalars(select(SchoolCalendarDay).where(
        SchoolCalendarDay.school_id == school_id, SchoolCalendarDay.calendar_date >= first, SchoolCalendarDay.calendar_date <= last
    )).all()
    if calendar_rows:
        required_dates = {r.calendar_date for r in calendar_rows if r.meal_required}
    else:
        required_dates = set(recorded_dates)  # backward-compatible until a calendar is configured
    verified_dates = {
        d for d in recorded_dates
        if d in attendance_by_date and d in meal_by_date
        and attendance_by_date[d].status == "VERIFIED"
        and meal_by_date[d].status == "VERIFIED"
    }
    verified_attendance = [attendance_by_date[d] for d in verified_dates]
    verified_meals = [meal_by_date[d] for d in verified_dates]
    return {
        "recorded_days": len(recorded_dates),
        "verified_days": len(verified_dates),
        "incomplete_days": len(required_dates - verified_dates),
        "attendance_class_1_5": sum(r.class_1_5_present for r in verified_attendance),
        "attendance_class_6_8": sum(r.class_6_8_present for r in verified_attendance),
        "meals_class_1_5": sum(r.meals_class_1_5 for r in verified_meals),
        "meals_class_6_8": sum(r.meals_class_6_8 for r in verified_meals),
        "total_meals": sum(r.total_meals for r in verified_meals),
        "tasting_exception_days": sum(1 for r in meal_rows if not r.tasting_done),
        "hygiene_exception_days": sum(1 for r in meal_rows if not r.hygiene_ok),
    }


@router.get("/hierarchy/scope")
def hierarchy_scope(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    school_ids = _accessible_school_ids(db, user)
    schools = []
    if school_ids:
        rows = db.scalars(
            select(School).where(School.id.in_(school_ids)).order_by(School.name_en)
        ).all()
        for school in rows:
            cluster = school.cluster
            block = cluster.block if cluster else None
            district = block.district if block else None
            schools.append({
                "school_id": school.id,
                "school_code": school.code,
                "udise_code": school.udise_code,
                "school_name_en": school.name_en,
                "school_name_mr": school.name_mr,
                "cluster_id": cluster.id if cluster else None,
                "cluster_name_en": cluster.name_en if cluster else None,
                "cluster_name_mr": cluster.name_mr if cluster else None,
                "block_id": block.id if block else None,
                "block_name_en": block.name_en if block else None,
                "block_name_mr": block.name_mr if block else None,
                "district_id": district.id if district else None,
                "district_name_en": district.name_en if district else None,
                "district_name_mr": district.name_mr if district else None,
            })
    org_access = db.scalars(select(UserOrgAccess).where(
        UserOrgAccess.keycloak_subject == user.subject,
        UserOrgAccess.active.is_(True),
    )).all()
    return {
        "roles": sorted(user.roles),
        "school_count": len(schools),
        "schools": schools,
        "org_access": [
            {
                "id": r.id,
                "role": r.role,
                "scope_key": r.scope_key,
                "district_id": r.district_id,
                "district_name_en": r.district.name_en if r.district else None,
                "district_name_mr": r.district.name_mr if r.district else None,
                "block_id": r.block_id,
                "block_name_en": r.block.name_en if r.block else None,
                "block_name_mr": r.block.name_mr if r.block else None,
                "cluster_id": r.cluster_id,
                "cluster_name_en": r.cluster.name_en if r.cluster else None,
                "cluster_name_mr": r.cluster.name_mr if r.cluster else None,
            }
            for r in org_access
        ],
    }


@router.get("/user-org-access")
def list_user_org_access(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_roles("SYSTEM_ADMIN")),
):
    rows = db.scalars(select(UserOrgAccess).where(UserOrgAccess.active.is_(True)).order_by(UserOrgAccess.username, UserOrgAccess.role)).all()
    return [{
        "id": r.id,
        "keycloak_subject": r.keycloak_subject,
        "username": r.username,
        "role": r.role,
        "scope_key": r.scope_key,
        "district_id": r.district_id,
        "block_id": r.block_id,
        "cluster_id": r.cluster_id,
    } for r in rows]


@router.post("/user-org-access")
def create_user_org_access(
    payload: OrgAccessInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("SYSTEM_ADMIN")),
):
    allowed = {"CLUSTER_OFFICER", "BLOCK_OFFICER", "DISTRICT_OFFICER"}
    if payload.role not in allowed:
        raise HTTPException(status_code=400, detail="Role must be CLUSTER_OFFICER, BLOCK_OFFICER or DISTRICT_OFFICER")
    chosen = [bool(payload.cluster_id), bool(payload.block_id), bool(payload.district_id)]
    if sum(chosen) != 1:
        raise HTTPException(status_code=400, detail="Exactly one hierarchy scope must be supplied")
    expected = {
        "CLUSTER_OFFICER": ("CLUSTER", payload.cluster_id),
        "BLOCK_OFFICER": ("BLOCK", payload.block_id),
        "DISTRICT_OFFICER": ("DISTRICT", payload.district_id),
    }[payload.role]
    if not expected[1]:
        raise HTTPException(status_code=400, detail=f"{expected[0].lower()} scope is required for {payload.role}")
    if payload.cluster_id and not db.get(Cluster, payload.cluster_id):
        raise HTTPException(status_code=404, detail="Cluster not found")
    if payload.block_id and not db.get(Block, payload.block_id):
        raise HTTPException(status_code=404, detail="Block not found")
    if payload.district_id and not db.get(District, payload.district_id):
        raise HTTPException(status_code=404, detail="District not found")
    scope_key = f"{expected[0]}:{expected[1]}"
    existing = db.scalar(select(UserOrgAccess).where(
        UserOrgAccess.keycloak_subject == payload.keycloak_subject,
        UserOrgAccess.role == payload.role,
        UserOrgAccess.scope_key == scope_key,
    ))
    if existing:
        existing.active = True
        existing.username = payload.username
        row = existing
    else:
        row = UserOrgAccess(
            keycloak_subject=payload.keycloak_subject,
            username=payload.username,
            role=payload.role,
            scope_key=scope_key,
            district_id=payload.district_id,
            block_id=payload.block_id,
            cluster_id=payload.cluster_id,
            created_by=user.username,
        )
        db.add(row)
    db.commit(); db.refresh(row)
    return {"ok": True, "id": row.id, "scope_key": row.scope_key}


@router.get("/monthly-returns")
def list_monthly_returns(
    year: int,
    month: int,
    school_id: str | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    if month < 1 or month > 12 or year < 2000 or year > 2200:
        raise HTTPException(status_code=400, detail="Invalid year/month")
    accessible = _accessible_school_ids(db, user)
    if not accessible:
        return []
    if school_id:
        _assert_school_access(db, user, school_id)
        accessible = [school_id]
    rows = db.scalars(
        select(MonthlySchoolReturn)
        .where(
            MonthlySchoolReturn.school_id.in_(accessible),
            MonthlySchoolReturn.year == year,
            MonthlySchoolReturn.month == month,
        )
        .order_by(MonthlySchoolReturn.status, MonthlySchoolReturn.school_id)
    ).all()
    return [_return_dict(r) for r in rows]


@router.get("/monthly-returns/summary")
def monthly_returns_summary(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    if month < 1 or month > 12 or year < 2000 or year > 2200:
        raise HTTPException(status_code=400, detail="Invalid year/month")
    accessible = _accessible_school_ids(db, user)
    total_schools = len(accessible)
    counts = {"DRAFT": 0, "SUBMITTED": 0, "CLUSTER_REVIEWED": 0, "BLOCK_APPROVED": 0, "RETURNED": 0}
    total_meals = 0
    incomplete_returns = 0
    if accessible:
        rows = db.scalars(select(MonthlySchoolReturn).where(
            MonthlySchoolReturn.school_id.in_(accessible),
            MonthlySchoolReturn.year == year,
            MonthlySchoolReturn.month == month,
        )).all()
        for r in rows:
            counts[r.status] = counts.get(r.status, 0) + 1
            total_meals += r.total_meals
            if r.incomplete_days > 0 or r.tasting_exception_days > 0 or r.hygiene_exception_days > 0:
                incomplete_returns += 1
    else:
        rows = []
    return {
        "year": year,
        "month": month,
        "total_schools": total_schools,
        "returns_generated": len(rows),
        "missing_returns": max(0, total_schools - len(rows)),
        "status_counts": counts,
        "total_meals": total_meals,
        "exception_returns": incomplete_returns,
    }


@router.post("/monthly-returns/generate")
def generate_monthly_return(
    payload: MonthlyGenerateInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("HEADMASTER", "SYSTEM_ADMIN")),
):
    _school_or_404(db, payload.school_id)
    _assert_school_access(db, user, payload.school_id)
    existing = db.scalar(select(MonthlySchoolReturn).where(
        MonthlySchoolReturn.school_id == payload.school_id,
        MonthlySchoolReturn.year == payload.year,
        MonthlySchoolReturn.month == payload.month,
    ))
    if existing and existing.status not in {"DRAFT", "RETURNED"}:
        raise HTTPException(status_code=409, detail="Submitted/reviewed return cannot be regenerated")
    metrics = _monthly_metrics(db, payload.school_id, payload.year, payload.month)
    now = datetime.now(timezone.utc)
    row = existing or MonthlySchoolReturn(
        school_id=payload.school_id,
        year=payload.year,
        month=payload.month,
        generated_by_subject=user.subject,
        generated_by_username=user.username,
        generated_at=now,
        created_by=user.username,
    )
    if not existing:
        db.add(row)
        db.flush()
    previous = row.status if existing else None
    for field, value in metrics.items():
        setattr(row, field, value)
    row.status = "DRAFT"
    row.generated_by_subject = user.subject
    row.generated_by_username = user.username
    row.generated_at = now
    row.return_reason = None
    _append_return_action(db, row, user, "REGENERATE" if existing else "GENERATE", previous, "DRAFT")
    db.commit(); db.refresh(row)
    return _return_dict(row)


@router.post("/monthly-returns/{return_id}/submit")
def submit_monthly_return(
    return_id: str,
    payload: MonthlyActionInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("HEADMASTER", "SYSTEM_ADMIN")),
):
    row = db.get(MonthlySchoolReturn, return_id)
    if not row:
        raise HTTPException(status_code=404, detail="Monthly return not found")
    _assert_school_access(db, user, row.school_id)
    if row.status not in {"DRAFT", "RETURNED"}:
        raise HTTPException(status_code=409, detail="Only draft/returned monthly return can be submitted")
    if row.verified_days <= 0:
        raise HTTPException(status_code=400, detail="At least one verified daily operation is required")
    if row.incomplete_days > 0 or row.tasting_exception_days > 0 or row.hygiene_exception_days > 0:
        raise HTTPException(status_code=409, detail="Resolve incomplete daily entries and tasting/hygiene exceptions before submission")
    previous = row.status
    now = datetime.now(timezone.utc)
    row.status = "SUBMITTED"
    row.submitted_by_subject = user.subject
    row.submitted_by_username = user.username
    row.submitted_at = now
    row.return_reason = None
    _append_return_action(db, row, user, "SUBMIT", previous, row.status, payload.remarks)
    db.commit(); db.refresh(row)
    return _return_dict(row)


@router.post("/monthly-returns/{return_id}/cluster-review")
def cluster_review_monthly_return(
    return_id: str,
    payload: MonthlyActionInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("CLUSTER_OFFICER", "SYSTEM_ADMIN")),
):
    row = db.get(MonthlySchoolReturn, return_id)
    if not row:
        raise HTTPException(status_code=404, detail="Monthly return not found")
    _assert_school_access(db, user, row.school_id)
    if row.status != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Return must be SUBMITTED before cluster review")
    previous = row.status
    row.status = "CLUSTER_REVIEWED"
    row.cluster_reviewed_by = user.username
    row.cluster_reviewed_at = datetime.now(timezone.utc)
    _append_return_action(db, row, user, "CLUSTER_REVIEW", previous, row.status, payload.remarks)
    db.commit(); db.refresh(row)
    return _return_dict(row)


@router.post("/monthly-returns/{return_id}/block-approve")
def block_approve_monthly_return(
    return_id: str,
    payload: MonthlyActionInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("BLOCK_OFFICER", "SYSTEM_ADMIN")),
):
    row = db.get(MonthlySchoolReturn, return_id)
    if not row:
        raise HTTPException(status_code=404, detail="Monthly return not found")
    _assert_school_access(db, user, row.school_id)
    if row.status != "CLUSTER_REVIEWED":
        raise HTTPException(status_code=409, detail="Return must be CLUSTER_REVIEWED before block approval")
    previous = row.status
    row.status = "BLOCK_APPROVED"
    row.block_approved_by = user.username
    row.block_approved_at = datetime.now(timezone.utc)
    _append_return_action(db, row, user, "BLOCK_APPROVE", previous, row.status, payload.remarks)
    db.commit(); db.refresh(row)
    return _return_dict(row)


@router.post("/monthly-returns/{return_id}/return")
def return_monthly_return(
    return_id: str,
    payload: MonthlyActionInput,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("CLUSTER_OFFICER", "BLOCK_OFFICER", "SYSTEM_ADMIN")),
):
    row = db.get(MonthlySchoolReturn, return_id)
    if not row:
        raise HTTPException(status_code=404, detail="Monthly return not found")
    _assert_school_access(db, user, row.school_id)
    if row.status not in {"SUBMITTED", "CLUSTER_REVIEWED"}:
        raise HTTPException(status_code=409, detail="Only submitted/reviewed return can be returned")
    if not payload.remarks or not payload.remarks.strip():
        raise HTTPException(status_code=400, detail="Return reason is required")
    previous = row.status
    row.status = "RETURNED"
    row.return_reason = payload.remarks.strip()
    _append_return_action(db, row, user, "RETURN", previous, row.status, payload.remarks)
    db.commit(); db.refresh(row)
    return _return_dict(row)


# ---------------- Phase 3B: Administrative dashboards & consolidated reporting ----------------

def _admin_school_snapshot(db: Session, user: CurrentUser, year: int, month: int):
    school_ids = _accessible_school_ids(db, user)
    if not school_ids:
        return []
    schools = db.scalars(select(School).where(School.id.in_(school_ids), School.active.is_(True))).all()
    returns = db.scalars(
        select(MonthlySchoolReturn).where(
            MonthlySchoolReturn.school_id.in_(school_ids),
            MonthlySchoolReturn.year == year,
            MonthlySchoolReturn.month == month,
        )
    ).all()
    ret_by_school = {str(r.school_id): r for r in returns}
    ingredients = db.scalars(
        select(Ingredient).where(Ingredient.track_inventory.is_(True), Ingredient.active.is_(True))
    ).all()
    rows = []
    for school in schools:
        cluster = school.cluster
        block = cluster.block if cluster else None
        district = block.district if block else None
        r = ret_by_school.get(str(school.id))
        low_items = 0
        for ing in ingredients:
            reorder = Decimal(str(ing.reorder_level or 0))
            if reorder <= 0:
                continue
            if _stock_balance(db, str(school.id), str(ing.id)) <= reorder:
                low_items += 1
        attendance = (r.attendance_class_1_5 + r.attendance_class_6_8) if r else 0
        meals = r.total_meals if r else 0
        exceptions = (r.incomplete_days + r.tasting_exception_days + r.hygiene_exception_days) if r else 0
        rows.append({
            "school_id": str(school.id),
            "school_name_en": school.name_en,
            "school_name_mr": school.name_mr,
            "udise_code": school.udise_code,
            "cluster_id": str(cluster.id) if cluster else None,
            "cluster_name_en": cluster.name_en if cluster else None,
            "cluster_name_mr": cluster.name_mr if cluster else None,
            "block_id": str(block.id) if block else None,
            "block_name_en": block.name_en if block else None,
            "block_name_mr": block.name_mr if block else None,
            "district_id": str(district.id) if district else None,
            "district_name_en": district.name_en if district else None,
            "district_name_mr": district.name_mr if district else None,
            "return_id": str(r.id) if r else None,
            "status": r.status if r else "MISSING",
            "recorded_days": r.recorded_days if r else 0,
            "verified_days": r.verified_days if r else 0,
            "attendance": attendance,
            "meals": meals,
            "coverage_pct": round((meals / attendance * 100), 2) if attendance > 0 else 0.0,
            "exceptions": exceptions,
            "low_stock_items": low_items,
            "has_low_stock": low_items > 0,
        })
    return rows


def _aggregate_admin_rows(rows: list[dict], level: str, parent_id: str | None = None):
    if level == "school":
        filtered = [r for r in rows if not parent_id or r.get("cluster_id") == parent_id]
        return [{
            "id": r["school_id"],
            "name_en": r["school_name_en"],
            "name_mr": r["school_name_mr"],
            "code": r["udise_code"],
            "school_count": 1,
            "returns_generated": 0 if r["status"] == "MISSING" else 1,
            "missing_returns": 1 if r["status"] == "MISSING" else 0,
            "approved_returns": 1 if r["status"] == "BLOCK_APPROVED" else 0,
            "pending_returns": 1 if r["status"] not in {"MISSING", "BLOCK_APPROVED"} else 0,
            "attendance": r["attendance"],
            "meals": r["meals"],
            "coverage_pct": r["coverage_pct"],
            "exception_schools": 1 if r["exceptions"] > 0 else 0,
            "low_stock_schools": 1 if r["has_low_stock"] else 0,
            "status": r["status"],
            "exceptions": r["exceptions"],
            "low_stock_items": r["low_stock_items"],
            "next_level": None,
        } for r in sorted(filtered, key=lambda x: x["school_name_en"])]

    spec = {
        "district": ("district_id", "district_name_en", "district_name_mr", None, "block"),
        "block": ("block_id", "block_name_en", "block_name_mr", "district_id", "cluster"),
        "cluster": ("cluster_id", "cluster_name_en", "cluster_name_mr", "block_id", "school"),
    }
    if level not in spec:
        raise HTTPException(status_code=400, detail="level must be district, block, cluster or school")
    id_key, en_key, mr_key, parent_key, next_level = spec[level]
    filtered = rows if not parent_key or not parent_id else [r for r in rows if r.get(parent_key) == parent_id]
    groups: dict[str, dict] = {}
    for r in filtered:
        gid = r.get(id_key)
        if not gid:
            continue
        g = groups.setdefault(gid, {
            "id": gid,
            "name_en": r.get(en_key) or "",
            "name_mr": r.get(mr_key) or "",
            "code": None,
            "school_count": 0,
            "returns_generated": 0,
            "missing_returns": 0,
            "approved_returns": 0,
            "pending_returns": 0,
            "attendance": 0,
            "meals": 0,
            "exception_schools": 0,
            "low_stock_schools": 0,
            "next_level": next_level,
        })
        g["school_count"] += 1
        if r["status"] == "MISSING":
            g["missing_returns"] += 1
        else:
            g["returns_generated"] += 1
            if r["status"] == "BLOCK_APPROVED":
                g["approved_returns"] += 1
            else:
                g["pending_returns"] += 1
        g["attendance"] += r["attendance"]
        g["meals"] += r["meals"]
        g["exception_schools"] += 1 if r["exceptions"] > 0 else 0
        g["low_stock_schools"] += 1 if r["has_low_stock"] else 0
    result = []
    for g in groups.values():
        g["coverage_pct"] = round((g["meals"] / g["attendance"] * 100), 2) if g["attendance"] else 0.0
        result.append(g)
    return sorted(result, key=lambda x: x["name_en"])


@router.get("/admin-dashboard/summary")
def admin_dashboard_summary(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    if not (user.roles & (OFFICER_ROLES | {"HEADMASTER"})):
        raise HTTPException(status_code=403, detail="Administrative dashboard access denied")
    if month < 1 or month > 12 or year < 2000 or year > 2200:
        raise HTTPException(status_code=400, detail="Invalid period")
    rows = _admin_school_snapshot(db, user, year, month)
    statuses: dict[str, int] = {"DRAFT": 0, "SUBMITTED": 0, "CLUSTER_REVIEWED": 0, "BLOCK_APPROVED": 0, "RETURNED": 0, "MISSING": 0}
    for r in rows:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    attendance = sum(r["attendance"] for r in rows)
    meals = sum(r["meals"] for r in rows)
    return {
        "year": year,
        "month": month,
        "total_schools": len(rows),
        "returns_generated": sum(1 for r in rows if r["status"] != "MISSING"),
        "missing_returns": sum(1 for r in rows if r["status"] == "MISSING"),
        "approved_returns": sum(1 for r in rows if r["status"] == "BLOCK_APPROVED"),
        "pending_returns": sum(1 for r in rows if r["status"] not in {"MISSING", "BLOCK_APPROVED"}),
        "total_attendance": attendance,
        "total_meals": meals,
        "meal_coverage_pct": round((meals / attendance * 100), 2) if attendance else 0.0,
        "exception_schools": sum(1 for r in rows if r["exceptions"] > 0),
        "low_stock_schools": sum(1 for r in rows if r["has_low_stock"]),
        "status_counts": statuses,
    }


@router.get("/admin-dashboard/drilldown")
def admin_dashboard_drilldown(
    year: int,
    month: int,
    level: str = "district",
    parent_id: str | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    if not (user.roles & (OFFICER_ROLES | {"HEADMASTER"})):
        raise HTTPException(status_code=403, detail="Administrative dashboard access denied")
    rows = _admin_school_snapshot(db, user, year, month)
    return {
        "level": level,
        "parent_id": parent_id,
        "rows": _aggregate_admin_rows(rows, level, parent_id),
    }


@router.get("/admin-dashboard/schools")
def admin_dashboard_schools(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    if not (user.roles & (OFFICER_ROLES | {"HEADMASTER"})):
        raise HTTPException(status_code=403, detail="Administrative dashboard access denied")
    return _admin_school_snapshot(db, user, year, month)


@router.get("/calendar/month")
def calendar_month(school_id: str, year: int, month: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _assert_school_access(db, user, school_id)
    first=date(year,month,1); last=date(year,month,monthrange(year,month)[1])
    rows=db.scalars(select(SchoolCalendarDay).where(SchoolCalendarDay.school_id==school_id,SchoolCalendarDay.calendar_date>=first,SchoolCalendarDay.calendar_date<=last).order_by(SchoolCalendarDay.calendar_date)).all()
    by={r.calendar_date:r for r in rows}; out=[]
    for n in range(1,last.day+1):
        d=date(year,month,n); r=by.get(d)
        default_type='SUNDAY' if d.weekday()==6 else 'WORKING'
        out.append({'date':d.isoformat(),'day_type':r.day_type if r else default_type,'meal_required':r.meal_required if r else d.weekday()!=6,'title_en':r.title_en if r else None,'title_mr':r.title_mr if r else None,'remarks':r.remarks if r else None,'configured':bool(r)})
    return out

@router.put("/calendar/day")
def calendar_day(payload: dict, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("HEADMASTER", "SYSTEM_ADMIN"))):
    school_id=str(payload.get('school_id','')); _assert_school_access(db,user,school_id)
    d=date.fromisoformat(str(payload['date'])); allowed={'WORKING','SUNDAY','PUBLIC_HOLIDAY','SCHOOL_HOLIDAY','LOCAL_HOLIDAY','CLOSURE','EXAM_NON_MEAL'}
    day_type=str(payload.get('day_type','WORKING')).upper()
    if day_type not in allowed: raise HTTPException(status_code=422,detail='Invalid day type')
    row=db.scalar(select(SchoolCalendarDay).where(SchoolCalendarDay.school_id==school_id,SchoolCalendarDay.calendar_date==d))
    if not row: row=SchoolCalendarDay(school_id=school_id,calendar_date=d,created_by=user.username); db.add(row)
    row.day_type=day_type; row.meal_required=bool(payload.get('meal_required',day_type=='WORKING')); row.title_en=payload.get('title_en'); row.title_mr=payload.get('title_mr'); row.remarks=payload.get('remarks')
    db.commit(); return {'status':'saved','date':d.isoformat()}

@router.post("/calendar/month/defaults")
def calendar_defaults(payload: dict, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("HEADMASTER", "SYSTEM_ADMIN"))):
    school_id=str(payload['school_id']); _assert_school_access(db,user,school_id); year=int(payload['year']); month=int(payload['month']); last=monthrange(year,month)[1]; created=0
    for n in range(1,last+1):
        d=date(year,month,n)
        row=db.scalar(select(SchoolCalendarDay.id).where(SchoolCalendarDay.school_id==school_id,SchoolCalendarDay.calendar_date==d))
        if row: continue
        sunday=d.weekday()==6
        db.add(SchoolCalendarDay(school_id=school_id,calendar_date=d,day_type='SUNDAY' if sunday else 'WORKING',meal_required=not sunday,created_by=user.username)); created+=1
    db.commit(); return {'status':'ok','created':created}

@router.get("/compliance/month")
def compliance_month(school_id: str, year: int, month: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _assert_school_access(db,user,school_id); first=date(year,month,1); last=date(year,month,monthrange(year,month)[1])
    cal=db.scalars(select(SchoolCalendarDay).where(SchoolCalendarDay.school_id==school_id,SchoolCalendarDay.calendar_date>=first,SchoolCalendarDay.calendar_date<=last)).all()
    required={r.calendar_date for r in cal if r.meal_required}
    meals=db.scalars(select(DailyMealEntry).where(DailyMealEntry.school_id==school_id,DailyMealEntry.meal_date>=first,DailyMealEntry.meal_date<=last)).all(); atts=db.scalars(select(DailyAttendance).where(DailyAttendance.school_id==school_id,DailyAttendance.meal_date>=first,DailyAttendance.meal_date<=last)).all()
    m={r.meal_date:r for r in meals}; a={r.meal_date:r for r in atts}; complete={d for d in required if d in m and d in a and m[d].status=='VERIFIED' and a[d].status=='VERIFIED'}; missing=sorted(required-complete)
    pct=round((len(complete)*100/len(required)),2) if required else 100.0
    return {'required_days':len(required),'complete_days':len(complete),'missing_days':len(missing),'compliance_percent':pct,'missing_dates':[d.isoformat() for d in missing]}
