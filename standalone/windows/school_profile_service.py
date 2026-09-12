from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

import admin_service
import runtime

ALLOWED_KITCHEN_TYPES = {"SCHOOL_KITCHEN", "CENTRAL_KITCHEN"}


def _now() -> str:
    return runtime.utc_now()


def ensure_schema() -> None:
    runtime.init_db()
    with runtime.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS school_profiles (
              id TEXT PRIMARY KEY,
              school_id TEXT NOT NULL UNIQUE REFERENCES schools(id) ON DELETE CASCADE,
              kitchen_type TEXT NOT NULL DEFAULT 'SCHOOL_KITCHEN',
              cooking_agency TEXT,
              headmaster_name TEXT,
              meal_incharge_name TEXT,
              contact_mobile TEXT,
              active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              CHECK (kitchen_type IN ('SCHOOL_KITCHEN','CENTRAL_KITCHEN'))
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS ix_school_profiles_school_id ON school_profiles(school_id)")


def _audit(conn: sqlite3.Connection, actor_id: str | None, action: str, entity_id: str, details: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (id, occurred_at, user_id, action, entity_type, entity_id, details_json)
        VALUES (?, ?, ?, ?, 'SCHOOL_PROFILE', ?, ?)
        """,
        (str(uuid.uuid4()), _now(), actor_id, action, entity_id, json.dumps(details, ensure_ascii=False, sort_keys=True)),
    )


def _require_school_access(user: dict[str, Any], school_id: str) -> dict[str, Any]:
    schools = admin_service.allowed_schools(user)
    school = next((row for row in schools if str(row.get("id")) == school_id), None)
    if not school:
        raise PermissionError("SCHOOL_ACCESS_DENIED")
    return school


def _clean_optional(value: Any, max_len: int, field: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > max_len:
        raise ValueError(f"{field}_TOO_LONG")
    return text


def _profile_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    result = dict(row)
    result["active"] = bool(result.get("active"))
    return result


def _assignments(conn: sqlite3.Connection, school_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          a.user_id AS id,
          u.username,
          u.display_name,
          u.role,
          a.preferred_language,
          a.active
        FROM local_user_school_access a
        JOIN local_users u ON u.id=a.user_id
        WHERE a.school_id=? AND a.active=1 AND u.active=1
        ORDER BY CASE u.role WHEN 'HEADMASTER' THEN 1 WHEN 'TEACHER' THEN 2 ELSE 3 END,
                 u.username
        """,
        (school_id,),
    ).fetchall()
    return [
        {
            "id": str(r["id"]),
            "username": str(r["username"]),
            "display_name": r["display_name"],
            "role": str(r["role"]),
            "preferred_language": str(r["preferred_language"] or "mr"),
        }
        for r in rows
    ]


def get_school_profile(school_id: str, user: dict[str, Any]) -> dict[str, Any]:
    ensure_schema()
    school_id = str(school_id or "").strip()
    if not school_id:
        raise ValueError("SCHOOL_ID_REQUIRED")
    school = _require_school_access(user, school_id)
    with runtime.connect() as conn:
        profile = conn.execute("SELECT * FROM school_profiles WHERE school_id=?", (school_id,)).fetchone()
        return {
            "school": school,
            "profile": _profile_dict(profile),
            "assignments": _assignments(conn, school_id),
        }


def upsert_school_profile(school_id: str, data: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    ensure_schema()
    school_id = str(school_id or "").strip()
    if not school_id:
        raise ValueError("SCHOOL_ID_REQUIRED")
    if user.get("role") not in {"SYSTEM_ADMIN", "HEADMASTER"}:
        raise PermissionError("HEADMASTER_REQUIRED")
    school = _require_school_access(user, school_id)

    kitchen_type = str(data.get("kitchen_type") or "SCHOOL_KITCHEN").strip().upper()
    if kitchen_type not in ALLOWED_KITCHEN_TYPES:
        raise ValueError("KITCHEN_TYPE_INVALID")
    values = {
        "kitchen_type": kitchen_type,
        "cooking_agency": _clean_optional(data.get("cooking_agency"), 200, "COOKING_AGENCY"),
        "headmaster_name": _clean_optional(data.get("headmaster_name"), 200, "HEADMASTER_NAME"),
        "meal_incharge_name": _clean_optional(data.get("meal_incharge_name"), 200, "MEAL_INCHARGE_NAME"),
        "contact_mobile": _clean_optional(data.get("contact_mobile"), 20, "CONTACT_MOBILE"),
    }
    if values["contact_mobile"] and not all(ch.isdigit() or ch in "+- ()" for ch in values["contact_mobile"]):
        raise ValueError("CONTACT_MOBILE_INVALID")

    now = _now()
    with runtime.connect() as conn:
        existing = conn.execute("SELECT * FROM school_profiles WHERE school_id=?", (school_id,)).fetchone()
        if existing:
            profile_id = str(existing["id"])
            conn.execute(
                """
                UPDATE school_profiles
                SET kitchen_type=?, cooking_agency=?, headmaster_name=?, meal_incharge_name=?,
                    contact_mobile=?, active=1, updated_at=?
                WHERE school_id=?
                """,
                (
                    values["kitchen_type"], values["cooking_agency"], values["headmaster_name"],
                    values["meal_incharge_name"], values["contact_mobile"], now, school_id,
                ),
            )
            action = "UPDATE"
        else:
            profile_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO school_profiles
                    (id, school_id, kitchen_type, cooking_agency, headmaster_name,
                     meal_incharge_name, contact_mobile, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    profile_id, school_id, values["kitchen_type"], values["cooking_agency"],
                    values["headmaster_name"], values["meal_incharge_name"], values["contact_mobile"], now, now,
                ),
            )
            action = "CREATE"
        _audit(conn, user.get("id"), action, profile_id, {"school_id": school_id, **values})
        profile = conn.execute("SELECT * FROM school_profiles WHERE school_id=?", (school_id,)).fetchone()
        return {
            "school": school,
            "profile": _profile_dict(profile),
            "assignments": _assignments(conn, school_id),
        }
