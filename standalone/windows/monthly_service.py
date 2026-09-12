from __future__ import annotations

import json
import sqlite3
import uuid
from calendar import monthrange
from datetime import date
from typing import Any

import runtime

STATUSES = {"DRAFT", "SUBMITTED", "CLUSTER_REVIEWED", "BLOCK_APPROVED", "RETURNED"}


def _now() -> str:
    return runtime.utc_now()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS monthly_school_returns (
          id TEXT PRIMARY KEY,
          school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
          year INTEGER NOT NULL,
          month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
          recorded_days INTEGER NOT NULL DEFAULT 0,
          verified_days INTEGER NOT NULL DEFAULT 0,
          incomplete_days INTEGER NOT NULL DEFAULT 0,
          attendance_class_1_5 INTEGER NOT NULL DEFAULT 0,
          attendance_class_6_8 INTEGER NOT NULL DEFAULT 0,
          meals_class_1_5 INTEGER NOT NULL DEFAULT 0,
          meals_class_6_8 INTEGER NOT NULL DEFAULT 0,
          total_meals INTEGER NOT NULL DEFAULT 0,
          tasting_exception_days INTEGER NOT NULL DEFAULT 0,
          hygiene_exception_days INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','SUBMITTED','CLUSTER_REVIEWED','BLOCK_APPROVED','RETURNED')),
          generated_by_user_id TEXT REFERENCES local_users(id) ON DELETE SET NULL,
          generated_by_username TEXT NOT NULL,
          generated_at TEXT NOT NULL,
          submitted_by_username TEXT,
          submitted_at TEXT,
          cluster_reviewed_by TEXT,
          cluster_reviewed_at TEXT,
          block_approved_by TEXT,
          block_approved_at TEXT,
          return_reason TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (school_id, year, month)
        );
        CREATE TABLE IF NOT EXISTS monthly_return_actions (
          id TEXT PRIMARY KEY,
          monthly_return_id TEXT NOT NULL REFERENCES monthly_school_returns(id) ON DELETE CASCADE,
          action TEXT NOT NULL,
          from_status TEXT,
          to_status TEXT NOT NULL,
          actor_user_id TEXT REFERENCES local_users(id) ON DELETE SET NULL,
          actor_username TEXT NOT NULL,
          actor_role TEXT NOT NULL,
          remarks TEXT,
          acted_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_monthly_returns_period ON monthly_school_returns(year, month, status);
        CREATE INDEX IF NOT EXISTS ix_monthly_returns_school ON monthly_school_returns(school_id, year, month);
        CREATE INDEX IF NOT EXISTS ix_monthly_return_actions_return ON monthly_return_actions(monthly_return_id, acted_at);
        """
    )


def _audit(conn: sqlite3.Connection, user: dict[str, Any], action: str, entity_id: str, details: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO audit_log (id, occurred_at, user_id, action, entity_type, entity_id, details_json) VALUES (?, ?, ?, ?, 'MONTHLY_RETURN', ?, ?)",
        (str(uuid.uuid4()), _now(), user.get("id"), action, entity_id, json.dumps(details, ensure_ascii=False, sort_keys=True)),
    )


def _period(year: int, month: int) -> tuple[str, str]:
    if year < 2000 or year > 2200 or month < 1 or month > 12:
        raise ValueError("MONTHLY_PERIOD_INVALID")
    return date(year, month, 1).isoformat(), date(year, month, monthrange(year, month)[1]).isoformat()


def _school(conn: sqlite3.Connection, school_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM schools WHERE id=? AND active=1", (school_id,)).fetchone()
    if not row:
        raise KeyError("SCHOOL_NOT_FOUND")
    return row


def _role(user: dict[str, Any], allowed: set[str], code: str) -> None:
    if str(user.get("role") or "") not in allowed:
        raise PermissionError(code)


def hierarchy_scope() -> dict[str, Any]:
    runtime.init_db()
    with runtime.connect() as conn:
        rows = conn.execute(
            """
            SELECT s.id AS school_id, s.name_en AS school_name_en, s.name_mr AS school_name_mr, s.udise_code,
                   c.id AS cluster_id, c.name_en AS cluster_name_en, c.name_mr AS cluster_name_mr,
                   b.id AS block_id, b.name_en AS block_name_en, b.name_mr AS block_name_mr,
                   d.id AS district_id, d.name_en AS district_name_en, d.name_mr AS district_name_mr
            FROM schools s
            JOIN clusters c ON c.id=s.cluster_id
            JOIN blocks b ON b.id=c.block_id
            JOIN districts d ON d.id=b.district_id
            WHERE s.active=1
            ORDER BY d.name_en,b.name_en,c.name_en,s.name_en
            """
        ).fetchall()
        return {"schools": [dict(r) for r in rows]}


def _row_dict(conn: sqlite3.Connection, return_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT r.*, s.name_en AS school_name_en, s.name_mr AS school_name_mr, s.udise_code,
               c.name_en AS cluster_name_en, c.name_mr AS cluster_name_mr,
               b.name_en AS block_name_en, b.name_mr AS block_name_mr,
               d.name_en AS district_name_en, d.name_mr AS district_name_mr
        FROM monthly_school_returns r
        JOIN schools s ON s.id=r.school_id
        JOIN clusters c ON c.id=s.cluster_id
        JOIN blocks b ON b.id=c.block_id
        JOIN districts d ON d.id=b.district_id
        WHERE r.id=?
        """,
        (return_id,),
    ).fetchone()
    if not row:
        raise KeyError("MONTHLY_RETURN_NOT_FOUND")
    return dict(row)


def list_monthly_returns(year: int, month: int) -> list[dict[str, Any]]:
    _period(year, month)
    runtime.init_db()
    with runtime.connect() as conn:
        _ensure_schema(conn)
        ids = [r[0] for r in conn.execute("SELECT id FROM monthly_school_returns WHERE year=? AND month=? ORDER BY created_at", (year, month)).fetchall()]
        return [_row_dict(conn, rid) for rid in ids]


def summary(year: int, month: int) -> dict[str, Any]:
    _period(year, month)
    runtime.init_db()
    with runtime.connect() as conn:
        _ensure_schema(conn)
        total_schools = int(conn.execute("SELECT COUNT(*) FROM schools WHERE active=1").fetchone()[0])
        rows = conn.execute("SELECT status,total_meals,incomplete_days,tasting_exception_days,hygiene_exception_days FROM monthly_school_returns WHERE year=? AND month=?", (year, month)).fetchall()
        status_counts = {s: 0 for s in sorted(STATUSES)}
        for row in rows:
            status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        return {
            "total_schools": total_schools,
            "returns_generated": len(rows),
            "missing_returns": max(0, total_schools - len(rows)),
            "status_counts": status_counts,
            "total_meals": sum(int(r["total_meals"] or 0) for r in rows),
            "exception_returns": sum(1 for r in rows if int(r["incomplete_days"] or 0) + int(r["tasting_exception_days"] or 0) + int(r["hygiene_exception_days"] or 0) > 0),
        }


def _aggregate(conn: sqlite3.Connection, school_id: str, year: int, month: int) -> dict[str, int]:
    first, last = _period(year, month)
    recorded_dates = {r[0] for r in conn.execute("SELECT meal_date FROM daily_attendance WHERE school_id=? AND meal_date BETWEEN ? AND ?", (school_id, first, last)).fetchall()}
    recorded_dates.update(r[0] for r in conn.execute("SELECT meal_date FROM daily_meal_entries WHERE school_id=? AND meal_date BETWEEN ? AND ?", (school_id, first, last)).fetchall())
    verified_dates = {
        r[0] for r in conn.execute(
            """
            SELECT a.meal_date FROM daily_attendance a
            JOIN daily_meal_entries m ON m.school_id=a.school_id AND m.meal_date=a.meal_date
            WHERE a.school_id=? AND a.meal_date BETWEEN ? AND ? AND a.status='VERIFIED' AND m.status='VERIFIED'
            """,
            (school_id, first, last),
        ).fetchall()
    }
    if verified_dates:
        marks = ",".join("?" for _ in verified_dates)
        params = [school_id, *sorted(verified_dates)]
        a = conn.execute(f"SELECT COALESCE(SUM(class_1_5_present),0),COALESCE(SUM(class_6_8_present),0) FROM daily_attendance WHERE school_id=? AND meal_date IN ({marks})", params).fetchone()
        m = conn.execute(f"SELECT COALESCE(SUM(meals_class_1_5),0),COALESCE(SUM(meals_class_6_8),0),COALESCE(SUM(total_meals),0),SUM(CASE WHEN tasting_done=0 THEN 1 ELSE 0 END),SUM(CASE WHEN hygiene_ok=0 THEN 1 ELSE 0 END) FROM daily_meal_entries WHERE school_id=? AND meal_date IN ({marks})", params).fetchone()
    else:
        a = (0, 0)
        m = (0, 0, 0, 0, 0)
    return {
        "recorded_days": len(recorded_dates),
        "verified_days": len(verified_dates),
        "incomplete_days": len(recorded_dates - verified_dates),
        "attendance_class_1_5": int(a[0] or 0),
        "attendance_class_6_8": int(a[1] or 0),
        "meals_class_1_5": int(m[0] or 0),
        "meals_class_6_8": int(m[1] or 0),
        "total_meals": int(m[2] or 0),
        "tasting_exception_days": int(m[3] or 0),
        "hygiene_exception_days": int(m[4] or 0),
    }


def generate(data: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    _role(user, {"HEADMASTER", "SYSTEM_ADMIN"}, "HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED")
    school_id = str(data.get("school_id") or "").strip()
    year, month = int(data.get("year") or 0), int(data.get("month") or 0)
    runtime.init_db()
    with runtime.connect() as conn:
        _ensure_schema(conn)
        _school(conn, school_id)
        agg = _aggregate(conn, school_id, year, month)
        existing = conn.execute("SELECT * FROM monthly_school_returns WHERE school_id=? AND year=? AND month=?", (school_id, year, month)).fetchone()
        now = _now()
        if existing and existing["status"] not in {"DRAFT", "RETURNED"}:
            raise ValueError("MONTHLY_RETURN_LOCKED_BY_WORKFLOW")
        if existing:
            return_id = existing["id"]
            conn.execute(
                """
                UPDATE monthly_school_returns SET recorded_days=?,verified_days=?,incomplete_days=?,attendance_class_1_5=?,attendance_class_6_8=?,meals_class_1_5=?,meals_class_6_8=?,total_meals=?,tasting_exception_days=?,hygiene_exception_days=?,generated_by_user_id=?,generated_by_username=?,generated_at=?,updated_at=? WHERE id=?
                """,
                (*agg.values(), user.get("id"), user.get("username") or "local", now, now, return_id),
            )
            action = "REFRESH"
        else:
            return_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO monthly_school_returns (id,school_id,year,month,recorded_days,verified_days,incomplete_days,attendance_class_1_5,attendance_class_6_8,meals_class_1_5,meals_class_6_8,total_meals,tasting_exception_days,hygiene_exception_days,status,generated_by_user_id,generated_by_username,generated_at,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'DRAFT',?,?,?,?,?)
                """,
                (return_id, school_id, year, month, *agg.values(), user.get("id"), user.get("username") or "local", now, now, now),
            )
            action = "GENERATE"
        _audit(conn, user, action, return_id, {"school_id": school_id, "year": year, "month": month, **agg})
        return _row_dict(conn, return_id)


def _action(conn: sqlite3.Connection, return_id: str, action: str, to_status: str, user: dict[str, Any], remarks: str | None, allowed_from: set[str]) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM monthly_school_returns WHERE id=?", (return_id,)).fetchone()
    if not row:
        raise KeyError("MONTHLY_RETURN_NOT_FOUND")
    if row["status"] not in allowed_from:
        raise ValueError(f"MONTHLY_RETURN_STATUS_INVALID:{row['status']}")
    now = _now()
    fields = {"status": to_status, "updated_at": now}
    if action == "SUBMIT":
        fields.update(submitted_by_username=user.get("username"), submitted_at=now, return_reason=None)
    elif action == "CLUSTER_REVIEW":
        fields.update(cluster_reviewed_by=user.get("username"), cluster_reviewed_at=now)
    elif action == "BLOCK_APPROVE":
        fields.update(block_approved_by=user.get("username"), block_approved_at=now)
    elif action == "RETURN":
        fields.update(return_reason=remarks or "Returned for correction")
    set_sql = ",".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE monthly_school_returns SET {set_sql} WHERE id=?", (*fields.values(), return_id))
    conn.execute(
        "INSERT INTO monthly_return_actions (id,monthly_return_id,action,from_status,to_status,actor_user_id,actor_username,actor_role,remarks,acted_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), return_id, action, row["status"], to_status, user.get("id"), user.get("username") or "local", user.get("role") or "", remarks, now),
    )
    _audit(conn, user, action, return_id, {"from_status": row["status"], "to_status": to_status, "remarks": remarks})
    return _row_dict(conn, return_id)


def submit(return_id: str, user: dict[str, Any], remarks: str | None = None) -> dict[str, Any]:
    _role(user, {"HEADMASTER", "SYSTEM_ADMIN"}, "HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED")
    runtime.init_db()
    with runtime.connect() as conn:
        _ensure_schema(conn)
        return _action(conn, return_id, "SUBMIT", "SUBMITTED", user, remarks, {"DRAFT", "RETURNED"})


def cluster_review(return_id: str, user: dict[str, Any], remarks: str | None = None) -> dict[str, Any]:
    _role(user, {"CLUSTER_OFFICER", "SYSTEM_ADMIN"}, "CLUSTER_OFFICER_OR_SYSTEM_ADMIN_REQUIRED")
    runtime.init_db()
    with runtime.connect() as conn:
        _ensure_schema(conn)
        return _action(conn, return_id, "CLUSTER_REVIEW", "CLUSTER_REVIEWED", user, remarks, {"SUBMITTED"})


def block_approve(return_id: str, user: dict[str, Any], remarks: str | None = None) -> dict[str, Any]:
    _role(user, {"BLOCK_OFFICER", "SYSTEM_ADMIN"}, "BLOCK_OFFICER_OR_SYSTEM_ADMIN_REQUIRED")
    runtime.init_db()
    with runtime.connect() as conn:
        _ensure_schema(conn)
        return _action(conn, return_id, "BLOCK_APPROVE", "BLOCK_APPROVED", user, remarks, {"CLUSTER_REVIEWED"})


def return_for_correction(return_id: str, user: dict[str, Any], remarks: str | None = None) -> dict[str, Any]:
    _role(user, {"CLUSTER_OFFICER", "BLOCK_OFFICER", "SYSTEM_ADMIN"}, "REVIEW_OFFICER_OR_SYSTEM_ADMIN_REQUIRED")
    if not str(remarks or "").strip():
        raise ValueError("RETURN_REASON_REQUIRED")
    runtime.init_db()
    with runtime.connect() as conn:
        _ensure_schema(conn)
        return _action(conn, return_id, "RETURN", "RETURNED", user, str(remarks).strip(), {"SUBMITTED", "CLUSTER_REVIEWED"})


def report(return_id: str) -> dict[str, Any]:
    runtime.init_db()
    with runtime.connect() as conn:
        _ensure_schema(conn)
        row = _row_dict(conn, return_id)
        actions = [dict(r) for r in conn.execute("SELECT action,from_status,to_status,actor_username,actor_role,remarks,acted_at FROM monthly_return_actions WHERE monthly_return_id=? ORDER BY acted_at,id", (return_id,)).fetchall()]
        return {"report_type": "MONTHLY_RETURN", "generated_at": _now(), "return": row, "actions": actions}
