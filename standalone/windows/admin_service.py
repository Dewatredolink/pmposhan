from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

import runtime

ROLES = {"SYSTEM_ADMIN", "HEADMASTER", "TEACHER"}

# Recovered from the original PM POSHAN demo seed. This intentionally restores
# only ingredient/menu masters; it never recreates demo schools or demo users.
STANDARD_INGREDIENTS = [
    ("RICE", "Rice", "तांदूळ", "CEREAL_PULSE", "KG", True),
    ("MOONGDAL", "Moong Dal", "मुगडाळ", "CEREAL_PULSE", "KG", True),
    ("TURDAL", "Tur Dal", "तूरडाळ", "CEREAL_PULSE", "KG", True),
    ("MASOORDAL", "Masoor Dal", "मसूरडाळ", "CEREAL_PULSE", "KG", True),
    ("MATKI", "Matki", "मटकी", "SPROUT", "KG", True),
    ("MOONG", "Moong", "मूग", "SPROUT", "KG", True),
    ("CHAWLI", "Chawli", "चवळी", "SPROUT", "KG", True),
    ("HARBHARA", "Harbhara", "हरभरा", "SPROUT", "KG", True),
    ("VATANA", "Peas", "वाटाणा", "SPROUT", "KG", True),
    ("SOYA", "Soyabean", "सोयाबीन", "SPROUT", "KG", True),
    ("CUMIN", "Cumin", "जिरे", "SPICE", "KG", True),
    ("MUSTARD", "Mustard", "मोहरी", "SPICE", "KG", True),
    ("TURMERIC", "Turmeric", "हळद", "SPICE", "KG", True),
    ("GARAM", "Garam Masala", "गरम मसाला", "SPICE", "KG", True),
    ("OIL", "Oil", "तेल", "CONSUMABLE", "L", True),
    ("SALT", "Salt", "मीठ", "CONSUMABLE", "KG", True),
    ("SUGAR", "Sugar/Jaggery", "साखर/गुळ", "CONSUMABLE", "KG", True),
    ("MILK", "Milk Powder", "दूध पावडर", "CONSUMABLE", "KG", True),
    ("RAGI", "Ragi", "नाचणी", "CONSUMABLE", "KG", True),
    ("EGG", "Eggs", "अंडी", "OTHER", "EA", True),
    ("VEGETABLE", "Vegetable Cost", "भाजीपाला खर्च", "OTHER", "INR", False),
    ("FUEL", "Fuel Cost", "इंधन खर्च", "OTHER", "INR", False),
]

STANDARD_MENUS = [
    ("VPUL-W13-MON", "Vegetable Pulao", "व्हेज पुलाव", "W13", 1),
    ("MDKH-W13-TUE", "Moong Dal Khichdi", "मुगडाळ खिचडी", "W13", 2),
    ("CHPUL-W13-WED", "Chana Pulao", "चना पुलाव", "W13", 3),
    ("MBHAT-W13-THU", "Masale Bhat", "मसाले भात", "W13", 4),
    ("CHKH-W13-FRI", "Chawli Khichdi", "चवळी खिचडी", "W13", 5),
    ("MUSAL-W13-SAT", "Matki Usal", "मटकी उसळ", "W13", 6),
    ("MTPUL-W24-MON", "Matar Pulao", "मटर पुलाव", "W24", 1),
    ("MDVB-W24-TUE", "Moong Drumstick Varan Bhat", "मुग शेवगा वरणभात", "W24", 2),
    ("SOYP-W24-WED", "Soya Pulao", "सोया पुलाव", "W24", 3),
    ("VPUL-W24-THU", "Vegetable Pulao", "व्हेज पुलाव", "W24", 4),
    ("MDKH-W24-FRI", "Moong Dal Khichdi", "मुगडाळ खिचडी", "W24", 5),
    ("MASP-W24-SAT", "Masoor Pulao", "मसुरी पुलाव", "W24", 6),
]


def _now() -> str:
    return runtime.utc_now()


def ensure_admin_schema() -> None:
    runtime.init_db()
    with runtime.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS local_user_school_access (
              user_id TEXT NOT NULL REFERENCES local_users(id) ON DELETE CASCADE,
              school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
              preferred_language TEXT NOT NULL DEFAULT 'mr' CHECK (preferred_language IN ('mr','en')),
              active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (user_id, school_id)
            )
            """
        )


def _audit(conn: sqlite3.Connection, actor_id: str | None, action: str, entity_type: str, entity_id: str, details: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (id, occurred_at, user_id, action, entity_type, entity_id, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), _now(), actor_id, action, entity_type, entity_id, json.dumps(details, ensure_ascii=False, sort_keys=True)),
    )


def _validate_school_ids(conn: sqlite3.Connection, school_ids: list[str]) -> list[str]:
    clean = list(dict.fromkeys(str(x).strip() for x in school_ids if str(x).strip()))
    if not clean:
        return []
    marks = ",".join("?" for _ in clean)
    found = {str(r[0]) for r in conn.execute(f"SELECT id FROM schools WHERE id IN ({marks})", clean).fetchall()}
    missing = [x for x in clean if x not in found]
    if missing:
        raise ValueError("SCHOOL_ACCESS_INVALID")
    return clean


def _replace_school_access(conn: sqlite3.Connection, user_id: str, school_ids: list[str], preferred_language: str = "mr") -> None:
    school_ids = _validate_school_ids(conn, school_ids)
    conn.execute("DELETE FROM local_user_school_access WHERE user_id=?", (user_id,))
    now = _now()
    for school_id in school_ids:
        conn.execute(
            """
            INSERT INTO local_user_school_access
                (user_id, school_id, preferred_language, active, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (user_id, school_id, preferred_language if preferred_language in {"mr", "en"} else "mr", now, now),
        )


def user_school_access(user: dict[str, Any]) -> list[dict[str, Any]]:
    ensure_admin_schema()
    with runtime.connect() as conn:
        if user.get("role") == "SYSTEM_ADMIN":
            rows = conn.execute(
                "SELECT id AS school_id, name_en AS school_name_en, name_mr AS school_name_mr FROM schools WHERE active=1 ORDER BY name_en"
            ).fetchall()
            return [
                {
                    **dict(r),
                    "role": "SYSTEM_ADMIN",
                    "preferred_language": "mr",
                }
                for r in rows
            ]
        rows = conn.execute(
            """
            SELECT a.school_id, s.name_en AS school_name_en, s.name_mr AS school_name_mr,
                   u.role, a.preferred_language
            FROM local_user_school_access a
            JOIN local_users u ON u.id=a.user_id
            JOIN schools s ON s.id=a.school_id
            WHERE a.user_id=? AND a.active=1 AND s.active=1
            ORDER BY s.name_en
            """,
            (user["id"],),
        ).fetchall()
        return [dict(r) for r in rows]


def allowed_schools(user: dict[str, Any]) -> list[dict[str, Any]]:
    ensure_admin_schema()
    with runtime.connect() as conn:
        if user.get("role") == "SYSTEM_ADMIN":
            rows = conn.execute(
                """
                SELECT s.*, c.code AS cluster_code, c.name_en AS cluster_name_en, c.name_mr AS cluster_name_mr,
                       b.id AS block_id, b.code AS block_code, b.name_en AS block_name_en, b.name_mr AS block_name_mr,
                       d.id AS district_id, d.code AS district_code, d.name_en AS district_name_en, d.name_mr AS district_name_mr
                FROM schools s
                JOIN clusters c ON c.id=s.cluster_id
                JOIN blocks b ON b.id=c.block_id
                JOIN districts d ON d.id=b.district_id
                ORDER BY s.name_en, s.code
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT s.*, c.code AS cluster_code, c.name_en AS cluster_name_en, c.name_mr AS cluster_name_mr,
                       b.id AS block_id, b.code AS block_code, b.name_en AS block_name_en, b.name_mr AS block_name_mr,
                       d.id AS district_id, d.code AS district_code, d.name_en AS district_name_en, d.name_mr AS district_name_mr
                FROM local_user_school_access a
                JOIN schools s ON s.id=a.school_id
                JOIN clusters c ON c.id=s.cluster_id
                JOIN blocks b ON b.id=c.block_id
                JOIN districts d ON d.id=b.district_id
                WHERE a.user_id=? AND a.active=1
                ORDER BY s.name_en, s.code
                """,
                (user["id"],),
            ).fetchall()
        return [dict(r) for r in rows]


def list_users() -> list[dict[str, Any]]:
    ensure_admin_schema()
    with runtime.connect() as conn:
        users = [dict(r) for r in conn.execute(
            "SELECT id, username, display_name, role, active, created_at, updated_at, last_login_at FROM local_users ORDER BY username"
        ).fetchall()]
        for user in users:
            rows = conn.execute(
                """
                SELECT a.school_id, s.name_en, s.name_mr, a.preferred_language
                FROM local_user_school_access a JOIN schools s ON s.id=a.school_id
                WHERE a.user_id=? AND a.active=1 ORDER BY s.name_en
                """,
                (user["id"],),
            ).fetchall()
            user["school_access"] = [dict(r) for r in rows]
            user["school_ids"] = [str(r["school_id"]) for r in rows]
            user["active"] = bool(user["active"])
        return users


def create_user(data: dict[str, Any], actor_id: str) -> dict[str, Any]:
    ensure_admin_schema()
    username = str(data.get("username") or "").strip().lower()
    display_name = str(data.get("display_name") or "").strip()
    password = str(data.get("password") or "")
    role = str(data.get("role") or "").strip().upper()
    preferred_language = str(data.get("preferred_language") or "mr").strip().lower()
    school_ids = list(data.get("school_ids") or [])
    if not username or role not in ROLES:
        raise ValueError("USER_FIELDS_REQUIRED")
    if role != "SYSTEM_ADMIN" and not school_ids:
        raise ValueError("USER_SCHOOL_REQUIRED")
    user_id = str(uuid.uuid4())
    now = _now()
    with runtime.connect() as conn:
        school_ids = _validate_school_ids(conn, school_ids)
        try:
            conn.execute(
                """
                INSERT INTO local_users
                    (id, username, password_hash, display_name, role, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (user_id, username, runtime._password_hash(password), display_name, role, now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("USERNAME_ALREADY_EXISTS") from exc
        _replace_school_access(conn, user_id, school_ids, preferred_language)
        _audit(conn, actor_id, "CREATE", "LOCAL_USER", user_id, {"username": username, "role": role, "school_ids": school_ids})
    return next(x for x in list_users() if x["id"] == user_id)


def _active_admin_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM local_users WHERE role='SYSTEM_ADMIN' AND active=1").fetchone()[0])


def update_user(user_id: str, data: dict[str, Any], actor_id: str) -> dict[str, Any]:
    ensure_admin_schema()
    with runtime.connect() as conn:
        current = conn.execute("SELECT * FROM local_users WHERE id=?", (user_id,)).fetchone()
        if not current:
            raise KeyError("USER_NOT_FOUND")
        role = str(data.get("role", current["role"])).strip().upper()
        if role not in ROLES:
            raise ValueError("USER_ROLE_INVALID")
        active = 1 if bool(data.get("active", bool(current["active"]))) else 0
        display_name = str(data.get("display_name", current["display_name"] or "")).strip()
        if user_id == actor_id and (role != "SYSTEM_ADMIN" or not active):
            raise ValueError("CANNOT_DISABLE_OR_DEMOTE_CURRENT_ADMIN")
        if current["role"] == "SYSTEM_ADMIN" and current["active"] and (role != "SYSTEM_ADMIN" or not active) and _active_admin_count(conn) <= 1:
            raise ValueError("LAST_SYSTEM_ADMIN_REQUIRED")
        school_ids = list(data.get("school_ids") or []) if "school_ids" in data else None
        if role != "SYSTEM_ADMIN" and school_ids is not None and not school_ids:
            raise ValueError("USER_SCHOOL_REQUIRED")
        conn.execute(
            "UPDATE local_users SET display_name=?, role=?, active=?, updated_at=? WHERE id=?",
            (display_name, role, active, _now(), user_id),
        )
        if school_ids is not None:
            _replace_school_access(conn, user_id, school_ids, str(data.get("preferred_language") or "mr"))
        _audit(conn, actor_id, "UPDATE", "LOCAL_USER", user_id, {"role": role, "active": bool(active), "school_ids": school_ids})
    return next(x for x in list_users() if x["id"] == user_id)


def reset_password(user_id: str, new_password: str, actor_id: str) -> dict[str, Any]:
    ensure_admin_schema()
    password_hash = runtime._password_hash(new_password)
    with runtime.connect() as conn:
        row = conn.execute("SELECT username FROM local_users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise KeyError("USER_NOT_FOUND")
        conn.execute("UPDATE local_users SET password_hash=?, updated_at=? WHERE id=?", (password_hash, _now(), user_id))
        _audit(conn, actor_id, "RESET_PASSWORD", "LOCAL_USER", user_id, {"username": row["username"]})
    return {"ok": True, "user_id": user_id}


def restore_standard_masters(actor_id: str) -> dict[str, Any]:
    runtime.init_db()
    created_ingredients = 0
    existing_ingredients = 0
    created_menus = 0
    existing_menus = 0
    now = _now()
    with runtime.connect() as conn:
        for code, name_en, name_mr, category, unit, track in STANDARD_INGREDIENTS:
            row = conn.execute("SELECT id FROM ingredients WHERE code=?", (code,)).fetchone()
            if row:
                existing_ingredients += 1
                conn.execute(
                    "UPDATE ingredients SET name_en=?, name_mr=?, category=?, base_unit=?, track_inventory=?, active=1, updated_at=? WHERE code=?",
                    (name_en, name_mr, category, unit, 1 if track else 0, now, code),
                )
            else:
                created_ingredients += 1
                conn.execute(
                    """
                    INSERT INTO ingredients
                        (id, code, name_en, name_mr, category, base_unit, reorder_level, safety_stock, track_inventory, active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, 1, ?, ?)
                    """,
                    (str(uuid.uuid4()), code, name_en, name_mr, category, unit, 1 if track else 0, now, now),
                )
        for code, name_en, name_mr, week_pattern, day_of_week in STANDARD_MENUS:
            row = conn.execute("SELECT id FROM menus WHERE code=?", (code,)).fetchone()
            if row:
                existing_menus += 1
                conn.execute(
                    "UPDATE menus SET name_en=?, name_mr=?, week_pattern=?, day_of_week=?, active=1, updated_at=? WHERE code=?",
                    (name_en, name_mr, week_pattern, day_of_week, now, code),
                )
            else:
                created_menus += 1
                conn.execute(
                    """
                    INSERT INTO menus (id, code, name_en, name_mr, week_pattern, day_of_week, active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (str(uuid.uuid4()), code, name_en, name_mr, week_pattern, day_of_week, now, now),
                )
        _audit(
            conn,
            actor_id,
            "RESTORE_STANDARD_MASTERS",
            "MASTER_DATA",
            "PM_POSHAN_STANDARD",
            {
                "ingredients_created": created_ingredients,
                "ingredients_existing": existing_ingredients,
                "menus_created": created_menus,
                "menus_existing": existing_menus,
            },
        )
    return {
        "ok": True,
        "ingredients_total": len(STANDARD_INGREDIENTS),
        "ingredients_created": created_ingredients,
        "ingredients_existing": existing_ingredients,
        "menus_total": len(STANDARD_MENUS),
        "menus_created": created_menus,
        "menus_existing": existing_menus,
    }
