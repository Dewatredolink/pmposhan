from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date
from typing import Any

import runtime


def _now() -> str:
    return runtime.utc_now()


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _audit(conn: sqlite3.Connection, user_id: str | None, action: str, entity_type: str, entity_id: str, details: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (id, occurred_at, user_id, action, entity_type, entity_id, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), _now(), user_id, action, entity_type, entity_id, json.dumps(details, ensure_ascii=False, sort_keys=True)),
    )


def list_schools() -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        rows = conn.execute(
            """
            SELECT
                s.id, s.code, s.udise_code, s.cluster_id, s.name_en, s.name_mr,
                s.village, s.class_1_5_strength, s.class_6_8_strength, s.active,
                s.created_at, s.updated_at,
                c.code AS cluster_code, c.name_en AS cluster_name_en, c.name_mr AS cluster_name_mr,
                b.id AS block_id, b.code AS block_code, b.name_en AS block_name_en, b.name_mr AS block_name_mr,
                d.id AS district_id, d.code AS district_code, d.name_en AS district_name_en, d.name_mr AS district_name_mr
            FROM schools s
            JOIN clusters c ON c.id = s.cluster_id
            JOIN blocks b ON b.id = c.block_id
            JOIN districts d ON d.id = b.district_id
            ORDER BY s.name_en, s.code
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_school(school_id: str) -> dict[str, Any] | None:
    runtime.init_db()
    with runtime.connect() as conn:
        row = conn.execute(
            """
            SELECT
                s.id, s.code, s.udise_code, s.cluster_id, s.name_en, s.name_mr,
                s.village, s.class_1_5_strength, s.class_6_8_strength, s.active,
                s.created_at, s.updated_at,
                c.code AS cluster_code, c.name_en AS cluster_name_en, c.name_mr AS cluster_name_mr,
                b.id AS block_id, b.code AS block_code, b.name_en AS block_name_en, b.name_mr AS block_name_mr,
                d.id AS district_id, d.code AS district_code, d.name_en AS district_name_en, d.name_mr AS district_name_mr
            FROM schools s
            JOIN clusters c ON c.id = s.cluster_id
            JOIN blocks b ON b.id = c.block_id
            JOIN districts d ON d.id = b.district_id
            WHERE s.id = ?
            """,
            (school_id,),
        ).fetchone()
        return _row_dict(row)


def _require_cluster(conn: sqlite3.Connection, cluster_id: str) -> None:
    row = conn.execute("SELECT id FROM clusters WHERE id=? AND active=1", (cluster_id,)).fetchone()
    if not row:
        raise ValueError("CLUSTER_NOT_FOUND")


def create_school(data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    runtime.init_db()
    required = ("code", "udise_code", "cluster_id", "name_en", "name_mr")
    if any(not str(data.get(key) or "").strip() for key in required):
        raise ValueError("SCHOOL_FIELDS_REQUIRED")

    school_id = str(uuid.uuid4())
    now = _now()
    with runtime.connect() as conn:
        _require_cluster(conn, str(data["cluster_id"]))
        try:
            conn.execute(
                """
                INSERT INTO schools
                    (id, code, udise_code, cluster_id, name_en, name_mr, village,
                     class_1_5_strength, class_6_8_strength, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    school_id,
                    str(data["code"]).strip(),
                    str(data["udise_code"]).strip(),
                    str(data["cluster_id"]),
                    str(data["name_en"]).strip(),
                    str(data["name_mr"]).strip(),
                    str(data.get("village") or "").strip() or None,
                    max(0, int(data.get("class_1_5_strength", 0))),
                    max(0, int(data.get("class_6_8_strength", 0))),
                    1 if data.get("active", True) else 0,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            message = str(exc).lower()
            if "udise_code" in message:
                raise ValueError("SCHOOL_UDISE_ALREADY_EXISTS") from exc
            if "schools.code" in message or "unique constraint failed: schools.code" in message:
                raise ValueError("SCHOOL_CODE_ALREADY_EXISTS") from exc
            raise ValueError("SCHOOL_CREATE_CONFLICT") from exc
        _audit(conn, user_id, "CREATE", "SCHOOL", school_id, {"code": data["code"], "udise_code": data["udise_code"]})

    result = get_school(school_id)
    if not result:
        raise RuntimeError("SCHOOL_CREATE_FAILED")
    return result


def update_school(school_id: str, data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    runtime.init_db()
    with runtime.connect() as conn:
        existing = conn.execute("SELECT * FROM schools WHERE id=?", (school_id,)).fetchone()
        if not existing:
            raise KeyError("SCHOOL_NOT_FOUND")

        cluster_id = str(data.get("cluster_id", existing["cluster_id"]))
        _require_cluster(conn, cluster_id)
        values = {
            "code": str(data.get("code", existing["code"])).strip(),
            "udise_code": str(data.get("udise_code", existing["udise_code"])).strip(),
            "cluster_id": cluster_id,
            "name_en": str(data.get("name_en", existing["name_en"])).strip(),
            "name_mr": str(data.get("name_mr", existing["name_mr"])).strip(),
            "village": str(data.get("village", existing["village"] or "")).strip() or None,
            "class_1_5_strength": max(0, int(data.get("class_1_5_strength", existing["class_1_5_strength"]))),
            "class_6_8_strength": max(0, int(data.get("class_6_8_strength", existing["class_6_8_strength"]))),
            "active": 1 if data.get("active", bool(existing["active"])) else 0,
        }
        if not values["code"] or not values["udise_code"] or not values["name_en"] or not values["name_mr"]:
            raise ValueError("SCHOOL_FIELDS_REQUIRED")
        try:
            conn.execute(
                """
                UPDATE schools
                SET code=?, udise_code=?, cluster_id=?, name_en=?, name_mr=?, village=?,
                    class_1_5_strength=?, class_6_8_strength=?, active=?, updated_at=?
                WHERE id=?
                """,
                (
                    values["code"], values["udise_code"], values["cluster_id"], values["name_en"], values["name_mr"],
                    values["village"], values["class_1_5_strength"], values["class_6_8_strength"], values["active"],
                    _now(), school_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            message = str(exc).lower()
            if "udise_code" in message:
                raise ValueError("SCHOOL_UDISE_ALREADY_EXISTS") from exc
            if "schools.code" in message or "unique constraint failed: schools.code" in message:
                raise ValueError("SCHOOL_CODE_ALREADY_EXISTS") from exc
            raise ValueError("SCHOOL_UPDATE_CONFLICT") from exc
        _audit(conn, user_id, "UPDATE", "SCHOOL", school_id, values)

    result = get_school(school_id)
    if not result:
        raise RuntimeError("SCHOOL_UPDATE_FAILED")
    return result


def _validate_year_dates(start_date: str, end_date: str) -> tuple[str, str]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except Exception as exc:
        raise ValueError("ACADEMIC_YEAR_DATE_INVALID") from exc
    if start > end:
        raise ValueError("ACADEMIC_YEAR_DATE_RANGE_INVALID")
    return start.isoformat(), end.isoformat()


def list_academic_years() -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        rows = conn.execute(
            "SELECT id, code, start_date, end_date, is_current, created_at, updated_at FROM academic_years ORDER BY start_date DESC, code DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def create_academic_year(data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    code = str(data.get("code") or "").strip()
    if not code:
        raise ValueError("ACADEMIC_YEAR_CODE_REQUIRED")
    start_date, end_date = _validate_year_dates(str(data.get("start_date") or ""), str(data.get("end_date") or ""))
    year_id = str(uuid.uuid4())
    now = _now()
    make_current = bool(data.get("is_current", False))

    runtime.init_db()
    with runtime.connect() as conn:
        try:
            if make_current:
                conn.execute("UPDATE academic_years SET is_current=0, updated_at=? WHERE is_current=1", (now,))
            conn.execute(
                """
                INSERT INTO academic_years (id, code, start_date, end_date, is_current, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (year_id, code, start_date, end_date, 1 if make_current else 0, now, now),
            )
        except sqlite3.IntegrityError as exc:
            if "academic_years.code" in str(exc).lower():
                raise ValueError("ACADEMIC_YEAR_CODE_ALREADY_EXISTS") from exc
            raise ValueError("ACADEMIC_YEAR_CREATE_CONFLICT") from exc
        _audit(conn, user_id, "CREATE", "ACADEMIC_YEAR", year_id, {"code": code, "is_current": make_current})
        row = conn.execute("SELECT * FROM academic_years WHERE id=?", (year_id,)).fetchone()
        return dict(row)


def update_academic_year(year_id: str, data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    runtime.init_db()
    with runtime.connect() as conn:
        existing = conn.execute("SELECT * FROM academic_years WHERE id=?", (year_id,)).fetchone()
        if not existing:
            raise KeyError("ACADEMIC_YEAR_NOT_FOUND")
        code = str(data.get("code", existing["code"])).strip()
        if not code:
            raise ValueError("ACADEMIC_YEAR_CODE_REQUIRED")
        start_date, end_date = _validate_year_dates(
            str(data.get("start_date", existing["start_date"])),
            str(data.get("end_date", existing["end_date"])),
        )
        is_current = bool(data.get("is_current", bool(existing["is_current"])))
        now = _now()
        try:
            if is_current:
                conn.execute("UPDATE academic_years SET is_current=0, updated_at=? WHERE is_current=1 AND id<>?", (now, year_id))
            conn.execute(
                "UPDATE academic_years SET code=?, start_date=?, end_date=?, is_current=?, updated_at=? WHERE id=?",
                (code, start_date, end_date, 1 if is_current else 0, now, year_id),
            )
        except sqlite3.IntegrityError as exc:
            if "academic_years.code" in str(exc).lower():
                raise ValueError("ACADEMIC_YEAR_CODE_ALREADY_EXISTS") from exc
            raise ValueError("ACADEMIC_YEAR_UPDATE_CONFLICT") from exc
        _audit(conn, user_id, "UPDATE", "ACADEMIC_YEAR", year_id, {"code": code, "is_current": is_current})
        row = conn.execute("SELECT * FROM academic_years WHERE id=?", (year_id,)).fetchone()
        return dict(row)


def make_academic_year_current(year_id: str, user_id: str | None) -> dict[str, Any]:
    runtime.init_db()
    with runtime.connect() as conn:
        existing = conn.execute("SELECT id FROM academic_years WHERE id=?", (year_id,)).fetchone()
        if not existing:
            raise KeyError("ACADEMIC_YEAR_NOT_FOUND")
        now = _now()
        conn.execute("UPDATE academic_years SET is_current=0, updated_at=? WHERE is_current=1", (now,))
        conn.execute("UPDATE academic_years SET is_current=1, updated_at=? WHERE id=?", (now, year_id))
        _audit(conn, user_id, "MAKE_CURRENT", "ACADEMIC_YEAR", year_id, {})
        row = conn.execute("SELECT * FROM academic_years WHERE id=?", (year_id,)).fetchone()
        return dict(row)
