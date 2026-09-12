from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date
from typing import Any

import master_service
import runtime


def _now() -> str:
    return runtime.utc_now()


def _audit(conn: sqlite3.Connection, user_id: str | None, action: str, entity_type: str, entity_id: str, details: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (id, occurred_at, user_id, action, entity_type, entity_id, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), _now(), user_id, action, entity_type, entity_id, json.dumps(details, ensure_ascii=False, sort_keys=True)),
    )


def _iso(value: str, code: str = "DATE_INVALID") -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except Exception as exc:
        raise ValueError(code) from exc


def _require_school(conn: sqlite3.Connection, school_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM schools WHERE id=? AND active=1", (school_id,)).fetchone()
    if not row:
        raise KeyError("SCHOOL_NOT_FOUND")
    return row


def _require_menu(conn: sqlite3.Connection, menu_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM menus WHERE id=? AND active=1", (menu_id,)).fetchone()
    if not row:
        raise KeyError("MENU_NOT_FOUND")
    return row


def list_menus() -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        rows = conn.execute(
            "SELECT id, code, name_en, name_mr, week_pattern, day_of_week, active FROM menus WHERE active=1 ORDER BY day_of_week, code"
        ).fetchall()
        return [dict(r) for r in rows]


def get_recipe_preview(menu_id: str, on_date: str, class_1_5: int, class_6_8: int) -> dict[str, Any]:
    on_date = _iso(on_date, "RECIPE_DATE_INVALID")
    c15 = max(0, int(class_1_5))
    c68 = max(0, int(class_6_8))
    standard = master_service.get_recipe_standard(menu_id, on_date)
    items: list[dict[str, Any]] = []
    for item in standard["items"]:
        q15 = float(item.get("qty_class_1_5", 0) or 0)
        q68 = float(item.get("qty_class_6_8", 0) or 0)
        r15 = q15 * c15
        r68 = q68 * c68
        if q15 == 0 and q68 == 0:
            continue
        items.append(
            {
                "ingredient_id": item["ingredient_id"],
                "code": item["code"],
                "name_en": item["name_en"],
                "name_mr": item["name_mr"],
                "unit": item["unit"],
                "qty_per_student_class_1_5": q15,
                "qty_per_student_class_6_8": q68,
                "required_class_1_5": r15,
                "required_class_6_8": r68,
                "required_total": r15 + r68,
            }
        )
    return {
        "menu_id": menu_id,
        "on_date": on_date,
        "class_1_5": c15,
        "class_6_8": c68,
        "items": items,
    }


def _planned_menu(conn: sqlite3.Connection, school_id: str, meal_date: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT ms.menu_id, m.code AS menu_code, m.name_en AS menu_name_en, m.name_mr AS menu_name_mr
        FROM menu_schedules ms JOIN menus m ON m.id=ms.menu_id
        WHERE ms.school_id=? AND ms.menu_date=? AND ms.active=1
        """,
        (school_id, meal_date),
    ).fetchone()
    return dict(row) if row else None


def get_daily_operations(school_id: str, meal_date: str) -> dict[str, Any]:
    meal_date = _iso(meal_date, "MEAL_DATE_INVALID")
    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        attendance = conn.execute(
            "SELECT * FROM daily_attendance WHERE school_id=? AND meal_date=?",
            (school_id, meal_date),
        ).fetchone()
        meal = conn.execute(
            "SELECT * FROM daily_meal_entries WHERE school_id=? AND meal_date=?",
            (school_id, meal_date),
        ).fetchone()
        return {
            "attendance": dict(attendance) if attendance else None,
            "meal": dict(meal) if meal else None,
            "planned_menu": _planned_menu(conn, school_id, meal_date),
        }


def save_attendance(data: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    school_id = str(data.get("school_id") or "").strip()
    meal_date = _iso(str(data.get("meal_date") or ""), "MEAL_DATE_INVALID")
    status = str(data.get("status") or "DRAFT").upper()
    if status not in {"DRAFT", "SUBMITTED"}:
        raise ValueError("ATTENDANCE_STATUS_INVALID")
    values = {
        "class_1_5_enrolled": max(0, int(data.get("class_1_5_enrolled", 0))),
        "class_1_5_present": max(0, int(data.get("class_1_5_present", 0))),
        "class_6_8_enrolled": max(0, int(data.get("class_6_8_enrolled", 0))),
        "class_6_8_present": max(0, int(data.get("class_6_8_present", 0))),
    }
    if values["class_1_5_present"] > values["class_1_5_enrolled"] or values["class_6_8_present"] > values["class_6_8_enrolled"]:
        raise ValueError("ATTENDANCE_PRESENT_EXCEEDS_ENROLLED")

    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        existing = conn.execute("SELECT * FROM daily_attendance WHERE school_id=? AND meal_date=?", (school_id, meal_date)).fetchone()
        if existing and existing["status"] == "VERIFIED":
            raise ValueError("ATTENDANCE_ALREADY_VERIFIED")
        row_id = existing["id"] if existing else str(uuid.uuid4())
        now = _now()
        if existing:
            conn.execute(
                """
                UPDATE daily_attendance
                SET class_1_5_enrolled=?, class_1_5_present=?, class_6_8_enrolled=?, class_6_8_present=?,
                    status=?, entered_by_user_id=?, entered_by_username=?, updated_at=?
                WHERE id=?
                """,
                (*values.values(), status, user["id"], user["username"], now, row_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO daily_attendance
                    (id, school_id, meal_date, class_1_5_enrolled, class_1_5_present, class_6_8_enrolled, class_6_8_present,
                     status, entered_by_user_id, entered_by_username, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row_id, school_id, meal_date, *values.values(), status, user["id"], user["username"], now, now),
            )
        _audit(conn, user["id"], "UPSERT", "DAILY_ATTENDANCE", row_id, {"school_id": school_id, "meal_date": meal_date, "status": status})
        return dict(conn.execute("SELECT * FROM daily_attendance WHERE id=?", (row_id,)).fetchone())


def save_meal(data: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    school_id = str(data.get("school_id") or "").strip()
    meal_date = _iso(str(data.get("meal_date") or ""), "MEAL_DATE_INVALID")
    menu_id = str(data.get("menu_id") or "").strip()
    status = str(data.get("status") or "DRAFT").upper()
    if status not in {"DRAFT", "SUBMITTED"}:
        raise ValueError("MEAL_STATUS_INVALID")
    m15 = max(0, int(data.get("meals_class_1_5", 0)))
    m68 = max(0, int(data.get("meals_class_6_8", 0)))
    tasting = bool(data.get("tasting_done", False))
    hygiene = bool(data.get("hygiene_ok", False))
    if status == "SUBMITTED" and (not tasting or not hygiene):
        raise ValueError("MEAL_CHECKS_REQUIRED")

    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        _require_menu(conn, menu_id)
        attendance = conn.execute("SELECT * FROM daily_attendance WHERE school_id=? AND meal_date=?", (school_id, meal_date)).fetchone()
        if attendance and m15 + m68 > int(attendance["class_1_5_present"]) + int(attendance["class_6_8_present"]):
            raise ValueError("MEALS_EXCEED_ATTENDANCE")
        existing = conn.execute("SELECT * FROM daily_meal_entries WHERE school_id=? AND meal_date=?", (school_id, meal_date)).fetchone()
        if existing and existing["status"] == "VERIFIED":
            raise ValueError("MEAL_ALREADY_VERIFIED")
        row_id = existing["id"] if existing else str(uuid.uuid4())
        now = _now()
        values = (menu_id, m15, m68, m15 + m68, 1 if tasting else 0, 1 if hygiene else 0, str(data.get("remarks") or "").strip() or None, status, user["id"], user["username"])
        if existing:
            conn.execute(
                """
                UPDATE daily_meal_entries
                SET menu_id=?, meals_class_1_5=?, meals_class_6_8=?, total_meals=?, tasting_done=?, hygiene_ok=?, remarks=?,
                    status=?, entered_by_user_id=?, entered_by_username=?, updated_at=? WHERE id=?
                """,
                (*values, now, row_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO daily_meal_entries
                    (id, school_id, meal_date, menu_id, meals_class_1_5, meals_class_6_8, total_meals, tasting_done, hygiene_ok,
                     remarks, status, entered_by_user_id, entered_by_username, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row_id, school_id, meal_date, *values, now, now),
            )
        _audit(conn, user["id"], "UPSERT", "DAILY_MEAL", row_id, {"school_id": school_id, "meal_date": meal_date, "status": status, "menu_id": menu_id})
        return dict(conn.execute("SELECT * FROM daily_meal_entries WHERE id=?", (row_id,)).fetchone())


def _balance(conn: sqlite3.Connection, school_id: str, ingredient_id: str) -> float:
    value = conn.execute(
        "SELECT COALESCE(SUM(quantity),0) FROM stock_transactions WHERE school_id=? AND ingredient_id=?",
        (school_id, ingredient_id),
    ).fetchone()[0]
    return float(value or 0)


def verify_daily_operations(school_id: str, meal_date: str, user: dict[str, Any]) -> dict[str, Any]:
    meal_date = _iso(meal_date, "MEAL_DATE_INVALID")
    if user.get("role") not in {"SYSTEM_ADMIN", "HEADMASTER"}:
        raise PermissionError("HEADMASTER_REQUIRED")

    runtime.init_db()
    with runtime.connect() as conn:
        attendance = conn.execute("SELECT * FROM daily_attendance WHERE school_id=? AND meal_date=?", (school_id, meal_date)).fetchone()
        meal = conn.execute("SELECT * FROM daily_meal_entries WHERE school_id=? AND meal_date=?", (school_id, meal_date)).fetchone()
        if not attendance or not meal:
            raise ValueError("DAILY_OPERATIONS_INCOMPLETE")
        if attendance["status"] == "VERIFIED" and meal["status"] == "VERIFIED":
            posted = conn.execute("SELECT COUNT(*) FROM stock_transactions WHERE reference_type='DAILY_MEAL' AND reference_id=? AND transaction_type='CONSUMPTION'", (meal["id"],)).fetchone()[0]
            return {"verified": True, "already_verified": True, "stock_consumption_transactions": int(posted), "verified_at": meal["verified_at"]}
        if attendance["status"] != "SUBMITTED" or meal["status"] != "SUBMITTED":
            raise ValueError("DAILY_OPERATIONS_NOT_SUBMITTED")
        if not meal["tasting_done"] or not meal["hygiene_ok"]:
            raise ValueError("MEAL_CHECKS_REQUIRED")

        preview = get_recipe_preview(meal["menu_id"], meal_date, int(meal["meals_class_1_5"]), int(meal["meals_class_6_8"]))
        tracked_items: list[dict[str, Any]] = []
        shortages: list[dict[str, Any]] = []
        for item in preview["items"]:
            ingredient = conn.execute("SELECT track_inventory FROM ingredients WHERE id=?", (item["ingredient_id"],)).fetchone()
            if not ingredient or not ingredient["track_inventory"]:
                continue
            required = float(item["required_total"])
            if required <= 0:
                continue
            available = _balance(conn, school_id, item["ingredient_id"])
            if available + 1e-9 < required:
                shortages.append({"ingredient_id": item["ingredient_id"], "code": item["code"], "required": required, "available": available, "unit": item["unit"]})
            tracked_items.append({**item, "available": available})
        if shortages:
            raise ValueError("INSUFFICIENT_STOCK:" + json.dumps(shortages, ensure_ascii=False, separators=(",", ":")))

        now = _now()
        posted = 0
        for item in tracked_items:
            transaction_id = str(uuid.uuid4())
            try:
                conn.execute(
                    """
                    INSERT INTO stock_transactions
                        (id, school_id, ingredient_id, transaction_date, transaction_type, quantity,
                         reference_type, reference_id, reference_no, remarks, entered_by_user_id, entered_by_username, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'CONSUMPTION', ?, 'DAILY_MEAL', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        transaction_id, school_id, item["ingredient_id"], meal_date, -float(item["required_total"]), meal["id"],
                        meal_date, "Automatic recipe consumption", user["id"], user["username"], now, now,
                    ),
                )
                posted += 1
            except sqlite3.IntegrityError:
                pass

        conn.execute(
            "UPDATE daily_attendance SET status='VERIFIED', verified_by_user_id=?, verified_by_username=?, verified_at=?, updated_at=? WHERE id=?",
            (user["id"], user["username"], now, now, attendance["id"]),
        )
        conn.execute(
            "UPDATE daily_meal_entries SET status='VERIFIED', verified_by_user_id=?, verified_by_username=?, verified_at=?, updated_at=? WHERE id=?",
            (user["id"], user["username"], now, now, meal["id"]),
        )
        _audit(conn, user["id"], "VERIFY", "DAILY_OPERATIONS", meal["id"], {"school_id": school_id, "meal_date": meal_date, "stock_transactions": posted})
        return {"verified": True, "already_verified": False, "stock_consumption_transactions": posted, "verified_at": now}
