from datetime import date, datetime, timezone
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
    Ingredient,
    Menu,
    Recipe,
    School,
    SchoolProfile,
    Translation,
    UserSchoolAccess,
    StockReceipt,
    StockReceiptLine,
    StockTransaction,
    StockAdjustment,
    PhysicalStockVerification,
    PhysicalStockVerificationLine,
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
    return {"status": "ok", "service": "pmposhan-api", "phase": "2C"}


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
