from __future__ import annotations

import json
import sqlite3
import uuid
from calendar import monthrange
from datetime import date
from typing import Any

import runtime

ALLOWED_DAY_TYPES = {
    "WORKING",
    "SUNDAY",
    "PUBLIC_HOLIDAY",
    "SCHOOL_HOLIDAY",
    "LOCAL_HOLIDAY",
    "CLOSURE",
    "EXAM_NON_MEAL",
}


def _now() -> str:
    return runtime.utc_now()


def _audit(
    conn: sqlite3.Connection,
    user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (id, occurred_at, user_id, action, entity_type, entity_id, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            _now(),
            user_id,
            action,
            entity_type,
            entity_id,
            json.dumps(details, ensure_ascii=False, sort_keys=True),
        ),
    )


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


def _parse_date(value: str, code: str = "DATE_INVALID") -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except Exception as exc:
        raise ValueError(code) from exc


def _validate_year_month(year: int, month: int) -> tuple[int, int]:
    if year < 2000 or year > 2200 or month < 1 or month > 12:
        raise ValueError("YEAR_MONTH_INVALID")
    return year, month


def _require_calendar_editor(user: dict[str, Any]) -> None:
    if user.get("role") not in {"HEADMASTER", "SYSTEM_ADMIN"}:
        raise PermissionError("HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED")


def _menu_plan_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "school_id": row["school_id"],
        "menu_date": row["menu_date"],
        "menu_id": row["menu_id"],
        "menu_code": row["menu_code"],
        "menu_name_en": row["menu_name_en"],
        "menu_name_mr": row["menu_name_mr"],
        "remarks": row["remarks"],
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_menu_plan(school_id: str, menu_date: str) -> dict[str, Any]:
    menu_date = _parse_date(menu_date, "MENU_DATE_INVALID")
    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        row = conn.execute(
            """
            SELECT ms.*, m.code AS menu_code, m.name_en AS menu_name_en, m.name_mr AS menu_name_mr
            FROM menu_schedules ms
            JOIN menus m ON m.id=ms.menu_id
            WHERE ms.school_id=? AND ms.menu_date=? AND ms.active=1
            """,
            (school_id, menu_date),
        ).fetchone()
        return {"plan": _menu_plan_dict(row)}


def save_menu_plan(data: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    _require_calendar_editor(user)
    school_id = str(data.get("school_id") or "").strip()
    menu_id = str(data.get("menu_id") or "").strip()
    menu_date = _parse_date(str(data.get("menu_date") or ""), "MENU_DATE_INVALID")
    remarks = str(data.get("remarks") or "").strip() or None
    if not school_id or not menu_id:
        raise ValueError("MENU_PLAN_FIELDS_REQUIRED")

    runtime.init_db()
    now = _now()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        _require_menu(conn, menu_id)
        existing = conn.execute(
            "SELECT id FROM menu_schedules WHERE school_id=? AND menu_date=?",
            (school_id, menu_date),
        ).fetchone()
        if existing:
            row_id = existing["id"]
            conn.execute(
                """
                UPDATE menu_schedules
                SET menu_id=?, remarks=?, active=1, updated_at=?
                WHERE id=?
                """,
                (menu_id, remarks, now, row_id),
            )
            action = "UPDATE"
        else:
            row_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO menu_schedules
                    (id, school_id, menu_date, menu_id, remarks, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (row_id, school_id, menu_date, menu_id, remarks, now, now),
            )
            action = "CREATE"
        _audit(
            conn,
            user.get("id"),
            action,
            "MENU_SCHEDULE",
            row_id,
            {"school_id": school_id, "menu_date": menu_date, "menu_id": menu_id},
        )
    return get_menu_plan(school_id, menu_date)


def _calendar_default_for_date(d: date) -> dict[str, Any]:
    sunday = d.weekday() == 6
    return {
        "date": d.isoformat(),
        "day_type": "SUNDAY" if sunday else "WORKING",
        "meal_required": not sunday,
        "title_en": None,
        "title_mr": None,
        "remarks": None,
        "configured": False,
    }


def calendar_month(school_id: str, year: int, month: int) -> list[dict[str, Any]]:
    year, month = _validate_year_month(int(year), int(month))
    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        first = date(year, month, 1)
        last = date(year, month, monthrange(year, month)[1])
        rows = conn.execute(
            """
            SELECT * FROM school_calendar_days
            WHERE school_id=? AND calendar_date>=? AND calendar_date<=?
            ORDER BY calendar_date
            """,
            (school_id, first.isoformat(), last.isoformat()),
        ).fetchall()
        configured = {row["calendar_date"]: row for row in rows}
        result: list[dict[str, Any]] = []
        for n in range(1, last.day + 1):
            d = date(year, month, n)
            row = configured.get(d.isoformat())
            if row:
                result.append(
                    {
                        "date": row["calendar_date"],
                        "day_type": row["day_type"],
                        "meal_required": bool(row["meal_required"]),
                        "title_en": row["title_en"],
                        "title_mr": row["title_mr"],
                        "remarks": row["remarks"],
                        "configured": True,
                    }
                )
            else:
                result.append(_calendar_default_for_date(d))
        return result


def create_month_defaults(data: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    _require_calendar_editor(user)
    school_id = str(data.get("school_id") or "").strip()
    year, month = _validate_year_month(int(data.get("year")), int(data.get("month")))
    if not school_id:
        raise ValueError("SCHOOL_ID_REQUIRED")

    runtime.init_db()
    now = _now()
    created = 0
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        last = monthrange(year, month)[1]
        for n in range(1, last + 1):
            d = date(year, month, n)
            if conn.execute(
                "SELECT id FROM school_calendar_days WHERE school_id=? AND calendar_date=?",
                (school_id, d.isoformat()),
            ).fetchone():
                continue
            sunday = d.weekday() == 6
            row_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO school_calendar_days
                    (id, school_id, calendar_date, day_type, meal_required, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    school_id,
                    d.isoformat(),
                    "SUNDAY" if sunday else "WORKING",
                    0 if sunday else 1,
                    now,
                    now,
                ),
            )
            created += 1
        _audit(
            conn,
            user.get("id"),
            "CREATE_MONTH_DEFAULTS",
            "SCHOOL_CALENDAR",
            f"{school_id}:{year:04d}-{month:02d}",
            {"school_id": school_id, "year": year, "month": month, "created": created},
        )
    return {"status": "ok", "created": created}


def save_calendar_day(data: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    _require_calendar_editor(user)
    school_id = str(data.get("school_id") or "").strip()
    calendar_date = _parse_date(str(data.get("date") or ""), "CALENDAR_DATE_INVALID")
    day_type = str(data.get("day_type") or "WORKING").strip().upper()
    if not school_id:
        raise ValueError("SCHOOL_ID_REQUIRED")
    if day_type not in ALLOWED_DAY_TYPES:
        raise ValueError("CALENDAR_DAY_TYPE_INVALID")
    meal_required = bool(data.get("meal_required", day_type == "WORKING"))
    title_en = str(data.get("title_en") or "").strip() or None
    title_mr = str(data.get("title_mr") or "").strip() or None
    remarks = str(data.get("remarks") or "").strip() or None

    runtime.init_db()
    now = _now()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        existing = conn.execute(
            "SELECT id FROM school_calendar_days WHERE school_id=? AND calendar_date=?",
            (school_id, calendar_date),
        ).fetchone()
        if existing:
            row_id = existing["id"]
            conn.execute(
                """
                UPDATE school_calendar_days
                SET day_type=?, meal_required=?, title_en=?, title_mr=?, remarks=?, updated_at=?
                WHERE id=?
                """,
                (day_type, 1 if meal_required else 0, title_en, title_mr, remarks, now, row_id),
            )
            action = "UPDATE"
        else:
            row_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO school_calendar_days
                    (id, school_id, calendar_date, day_type, meal_required, title_en, title_mr, remarks, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    school_id,
                    calendar_date,
                    day_type,
                    1 if meal_required else 0,
                    title_en,
                    title_mr,
                    remarks,
                    now,
                    now,
                ),
            )
            action = "CREATE"
        _audit(
            conn,
            user.get("id"),
            action,
            "SCHOOL_CALENDAR_DAY",
            row_id,
            {
                "school_id": school_id,
                "date": calendar_date,
                "day_type": day_type,
                "meal_required": meal_required,
            },
        )
    return {"status": "saved", "date": calendar_date}


def compliance_month(school_id: str, year: int, month: int) -> dict[str, Any]:
    year, month = _validate_year_month(int(year), int(month))
    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        first = date(year, month, 1).isoformat()
        last = date(year, month, monthrange(year, month)[1]).isoformat()
        required_rows = conn.execute(
            """
            SELECT calendar_date FROM school_calendar_days
            WHERE school_id=? AND calendar_date>=? AND calendar_date<=? AND meal_required=1
            ORDER BY calendar_date
            """,
            (school_id, first, last),
        ).fetchall()
        required = [row["calendar_date"] for row in required_rows]
        if not required:
            return {
                "required_days": 0,
                "complete_days": 0,
                "missing_days": 0,
                "compliance_percent": 100.0,
                "missing_dates": [],
            }

        placeholders = ",".join("?" for _ in required)
        completed_rows = conn.execute(
            f"""
            SELECT meal_date FROM daily_meal_entries
            WHERE school_id=? AND meal_date IN ({placeholders}) AND status='VERIFIED'
            """,
            (school_id, *required),
        ).fetchall()
        complete_set = {row["meal_date"] for row in completed_rows}
        complete = [d for d in required if d in complete_set]
        missing = [d for d in required if d not in complete_set]
        pct = round((len(complete) * 100.0 / len(required)), 2) if required else 100.0
        return {
            "required_days": len(required),
            "complete_days": len(complete),
            "missing_days": len(missing),
            "compliance_percent": pct,
            "missing_dates": missing,
        }
