from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date
from typing import Any

import operations
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


def _required_text(data: dict[str, Any], key: str, error: str) -> str:
    value = str(data.get(key) or "").strip()
    if not value:
        raise ValueError(error)
    return value


def _bool_int(value: Any, default: bool = True) -> int:
    if value is None:
        value = default
    return 1 if bool(value) else 0


def list_districts() -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM districts ORDER BY name_en, code").fetchall()]


def create_district(data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    district_id = str(uuid.uuid4())
    code = _required_text(data, "code", "DISTRICT_FIELDS_REQUIRED")
    name_en = _required_text(data, "name_en", "DISTRICT_FIELDS_REQUIRED")
    name_mr = _required_text(data, "name_mr", "DISTRICT_FIELDS_REQUIRED")
    now = _now()
    runtime.init_db()
    with runtime.connect() as conn:
        try:
            conn.execute(
                "INSERT INTO districts (id, code, name_en, name_mr, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (district_id, code, name_en, name_mr, _bool_int(data.get("active"), True), now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("DISTRICT_CODE_ALREADY_EXISTS") from exc
        _audit(conn, user_id, "CREATE", "DISTRICT", district_id, {"code": code})
        return dict(conn.execute("SELECT * FROM districts WHERE id=?", (district_id,)).fetchone())


def update_district(row_id: str, data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    runtime.init_db()
    with runtime.connect() as conn:
        existing = conn.execute("SELECT * FROM districts WHERE id=?", (row_id,)).fetchone()
        if not existing:
            raise KeyError("DISTRICT_NOT_FOUND")
        values = {
            "code": str(data.get("code", existing["code"])).strip(),
            "name_en": str(data.get("name_en", existing["name_en"])).strip(),
            "name_mr": str(data.get("name_mr", existing["name_mr"])).strip(),
            "active": _bool_int(data.get("active"), bool(existing["active"])),
        }
        if not values["code"] or not values["name_en"] or not values["name_mr"]:
            raise ValueError("DISTRICT_FIELDS_REQUIRED")
        try:
            conn.execute(
                "UPDATE districts SET code=?, name_en=?, name_mr=?, active=?, updated_at=? WHERE id=?",
                (values["code"], values["name_en"], values["name_mr"], values["active"], _now(), row_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("DISTRICT_CODE_ALREADY_EXISTS") from exc
        _audit(conn, user_id, "UPDATE", "DISTRICT", row_id, values)
        return dict(conn.execute("SELECT * FROM districts WHERE id=?", (row_id,)).fetchone())


def list_blocks() -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        rows = conn.execute(
            """
            SELECT b.*, d.code AS district_code, d.name_en AS district_name_en, d.name_mr AS district_name_mr
            FROM blocks b JOIN districts d ON d.id=b.district_id
            ORDER BY b.name_en, b.code
            """
        ).fetchall()
        return [dict(r) for r in rows]


def create_block(data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    row_id = str(uuid.uuid4())
    code = _required_text(data, "code", "BLOCK_FIELDS_REQUIRED")
    district_id = _required_text(data, "district_id", "BLOCK_FIELDS_REQUIRED")
    name_en = _required_text(data, "name_en", "BLOCK_FIELDS_REQUIRED")
    name_mr = _required_text(data, "name_mr", "BLOCK_FIELDS_REQUIRED")
    now = _now()
    runtime.init_db()
    with runtime.connect() as conn:
        if not conn.execute("SELECT id FROM districts WHERE id=?", (district_id,)).fetchone():
            raise ValueError("DISTRICT_NOT_FOUND")
        try:
            conn.execute(
                "INSERT INTO blocks (id, code, district_id, name_en, name_mr, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (row_id, code, district_id, name_en, name_mr, _bool_int(data.get("active"), True), now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("BLOCK_CODE_ALREADY_EXISTS") from exc
        _audit(conn, user_id, "CREATE", "BLOCK", row_id, {"code": code, "district_id": district_id})
    return next(r for r in list_blocks() if r["id"] == row_id)


def update_block(row_id: str, data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    runtime.init_db()
    with runtime.connect() as conn:
        existing = conn.execute("SELECT * FROM blocks WHERE id=?", (row_id,)).fetchone()
        if not existing:
            raise KeyError("BLOCK_NOT_FOUND")
        district_id = str(data.get("district_id", existing["district_id"])).strip()
        if not conn.execute("SELECT id FROM districts WHERE id=?", (district_id,)).fetchone():
            raise ValueError("DISTRICT_NOT_FOUND")
        values = {
            "code": str(data.get("code", existing["code"])).strip(),
            "district_id": district_id,
            "name_en": str(data.get("name_en", existing["name_en"])).strip(),
            "name_mr": str(data.get("name_mr", existing["name_mr"])).strip(),
            "active": _bool_int(data.get("active"), bool(existing["active"])),
        }
        if not values["code"] or not values["name_en"] or not values["name_mr"]:
            raise ValueError("BLOCK_FIELDS_REQUIRED")
        try:
            conn.execute(
                "UPDATE blocks SET code=?, district_id=?, name_en=?, name_mr=?, active=?, updated_at=? WHERE id=?",
                (values["code"], values["district_id"], values["name_en"], values["name_mr"], values["active"], _now(), row_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("BLOCK_CODE_ALREADY_EXISTS") from exc
        _audit(conn, user_id, "UPDATE", "BLOCK", row_id, values)
    return next(r for r in list_blocks() if r["id"] == row_id)


def list_clusters() -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        rows = conn.execute(
            """
            SELECT c.*, b.code AS block_code, b.name_en AS block_name_en, b.name_mr AS block_name_mr,
                   d.id AS district_id, d.code AS district_code, d.name_en AS district_name_en, d.name_mr AS district_name_mr
            FROM clusters c
            JOIN blocks b ON b.id=c.block_id
            JOIN districts d ON d.id=b.district_id
            ORDER BY c.name_en, c.code
            """
        ).fetchall()
        return [dict(r) for r in rows]


def create_cluster(data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    row_id = str(uuid.uuid4())
    code = _required_text(data, "code", "CLUSTER_FIELDS_REQUIRED")
    block_id = _required_text(data, "block_id", "CLUSTER_FIELDS_REQUIRED")
    name_en = _required_text(data, "name_en", "CLUSTER_FIELDS_REQUIRED")
    name_mr = _required_text(data, "name_mr", "CLUSTER_FIELDS_REQUIRED")
    now = _now()
    runtime.init_db()
    with runtime.connect() as conn:
        if not conn.execute("SELECT id FROM blocks WHERE id=?", (block_id,)).fetchone():
            raise ValueError("BLOCK_NOT_FOUND")
        try:
            conn.execute(
                "INSERT INTO clusters (id, code, block_id, name_en, name_mr, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (row_id, code, block_id, name_en, name_mr, _bool_int(data.get("active"), True), now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("CLUSTER_CODE_ALREADY_EXISTS") from exc
        _audit(conn, user_id, "CREATE", "CLUSTER", row_id, {"code": code, "block_id": block_id})
    return next(r for r in list_clusters() if r["id"] == row_id)


def update_cluster(row_id: str, data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    runtime.init_db()
    with runtime.connect() as conn:
        existing = conn.execute("SELECT * FROM clusters WHERE id=?", (row_id,)).fetchone()
        if not existing:
            raise KeyError("CLUSTER_NOT_FOUND")
        block_id = str(data.get("block_id", existing["block_id"])).strip()
        if not conn.execute("SELECT id FROM blocks WHERE id=?", (block_id,)).fetchone():
            raise ValueError("BLOCK_NOT_FOUND")
        values = {
            "code": str(data.get("code", existing["code"])).strip(),
            "block_id": block_id,
            "name_en": str(data.get("name_en", existing["name_en"])).strip(),
            "name_mr": str(data.get("name_mr", existing["name_mr"])).strip(),
            "active": _bool_int(data.get("active"), bool(existing["active"])),
        }
        if not values["code"] or not values["name_en"] or not values["name_mr"]:
            raise ValueError("CLUSTER_FIELDS_REQUIRED")
        try:
            conn.execute(
                "UPDATE clusters SET code=?, block_id=?, name_en=?, name_mr=?, active=?, updated_at=? WHERE id=?",
                (values["code"], values["block_id"], values["name_en"], values["name_mr"], values["active"], _now(), row_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("CLUSTER_CODE_ALREADY_EXISTS") from exc
        _audit(conn, user_id, "UPDATE", "CLUSTER", row_id, values)
    return next(r for r in list_clusters() if r["id"] == row_id)


def list_schools() -> list[dict[str, Any]]:
    return operations.list_schools()


def create_school(data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    return operations.create_school(data, user_id)


def update_school(row_id: str, data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    return operations.update_school(row_id, data, user_id)


def list_ingredients() -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM ingredients ORDER BY name_en, code").fetchall()]


def create_ingredient(data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    row_id = str(uuid.uuid4())
    code = _required_text(data, "code", "INGREDIENT_FIELDS_REQUIRED")
    name_en = _required_text(data, "name_en", "INGREDIENT_FIELDS_REQUIRED")
    name_mr = _required_text(data, "name_mr", "INGREDIENT_FIELDS_REQUIRED")
    category = _required_text(data, "category", "INGREDIENT_FIELDS_REQUIRED")
    base_unit = _required_text(data, "base_unit", "INGREDIENT_FIELDS_REQUIRED").upper()
    reorder_level = float(data.get("reorder_level", 0) or 0)
    safety_stock = float(data.get("safety_stock", 0) or 0)
    if reorder_level < 0 or safety_stock < 0:
        raise ValueError("INGREDIENT_QUANTITY_INVALID")
    now = _now()
    runtime.init_db()
    with runtime.connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO ingredients
                    (id, code, name_en, name_mr, category, base_unit, reorder_level, safety_stock,
                     track_inventory, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id, code, name_en, name_mr, category, base_unit, reorder_level, safety_stock,
                    _bool_int(data.get("track_inventory"), True), _bool_int(data.get("active"), True), now, now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("INGREDIENT_CODE_ALREADY_EXISTS") from exc
        _audit(conn, user_id, "CREATE", "INGREDIENT", row_id, {"code": code})
        return dict(conn.execute("SELECT * FROM ingredients WHERE id=?", (row_id,)).fetchone())


def update_ingredient(row_id: str, data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    runtime.init_db()
    with runtime.connect() as conn:
        existing = conn.execute("SELECT * FROM ingredients WHERE id=?", (row_id,)).fetchone()
        if not existing:
            raise KeyError("INGREDIENT_NOT_FOUND")
        values = {
            "code": str(data.get("code", existing["code"])).strip(),
            "name_en": str(data.get("name_en", existing["name_en"])).strip(),
            "name_mr": str(data.get("name_mr", existing["name_mr"])).strip(),
            "category": str(data.get("category", existing["category"])).strip(),
            "base_unit": str(data.get("base_unit", existing["base_unit"])).strip().upper(),
            "reorder_level": float(data.get("reorder_level", existing["reorder_level"])),
            "safety_stock": float(data.get("safety_stock", existing["safety_stock"])),
            "track_inventory": _bool_int(data.get("track_inventory"), bool(existing["track_inventory"])),
            "active": _bool_int(data.get("active"), bool(existing["active"])),
        }
        if any(not values[k] for k in ("code", "name_en", "name_mr", "category", "base_unit")):
            raise ValueError("INGREDIENT_FIELDS_REQUIRED")
        if values["reorder_level"] < 0 or values["safety_stock"] < 0:
            raise ValueError("INGREDIENT_QUANTITY_INVALID")
        try:
            conn.execute(
                """
                UPDATE ingredients
                SET code=?, name_en=?, name_mr=?, category=?, base_unit=?, reorder_level=?, safety_stock=?,
                    track_inventory=?, active=?, updated_at=?
                WHERE id=?
                """,
                (
                    values["code"], values["name_en"], values["name_mr"], values["category"], values["base_unit"],
                    values["reorder_level"], values["safety_stock"], values["track_inventory"], values["active"], _now(), row_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("INGREDIENT_CODE_ALREADY_EXISTS") from exc
        _audit(conn, user_id, "UPDATE", "INGREDIENT", row_id, values)
        return dict(conn.execute("SELECT * FROM ingredients WHERE id=?", (row_id,)).fetchone())


def list_menus() -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM menus ORDER BY name_en, code").fetchall()]


def _menu_values(data: dict[str, Any], existing: sqlite3.Row | None = None) -> dict[str, Any]:
    values = {
        "code": str(data.get("code", existing["code"] if existing else "")).strip(),
        "name_en": str(data.get("name_en", existing["name_en"] if existing else "")).strip(),
        "name_mr": str(data.get("name_mr", existing["name_mr"] if existing else "")).strip(),
        "week_pattern": str(data.get("week_pattern", existing["week_pattern"] if existing else "CUSTOM")).strip(),
        "day_of_week": int(data.get("day_of_week", existing["day_of_week"] if existing else 1)),
        "active": _bool_int(data.get("active"), bool(existing["active"]) if existing else True),
    }
    if any(not values[k] for k in ("code", "name_en", "name_mr", "week_pattern")):
        raise ValueError("MENU_FIELDS_REQUIRED")
    if values["day_of_week"] < 1 or values["day_of_week"] > 6:
        raise ValueError("MENU_DAY_INVALID")
    return values


def create_menu(data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    row_id = str(uuid.uuid4())
    values = _menu_values(data)
    now = _now()
    runtime.init_db()
    with runtime.connect() as conn:
        try:
            conn.execute(
                "INSERT INTO menus (id, code, name_en, name_mr, week_pattern, day_of_week, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (row_id, values["code"], values["name_en"], values["name_mr"], values["week_pattern"], values["day_of_week"], values["active"], now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("MENU_CODE_ALREADY_EXISTS") from exc
        _audit(conn, user_id, "CREATE", "MENU", row_id, {"code": values["code"]})
        return dict(conn.execute("SELECT * FROM menus WHERE id=?", (row_id,)).fetchone())


def update_menu(row_id: str, data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    runtime.init_db()
    with runtime.connect() as conn:
        existing = conn.execute("SELECT * FROM menus WHERE id=?", (row_id,)).fetchone()
        if not existing:
            raise KeyError("MENU_NOT_FOUND")
        values = _menu_values(data, existing)
        try:
            conn.execute(
                "UPDATE menus SET code=?, name_en=?, name_mr=?, week_pattern=?, day_of_week=?, active=?, updated_at=? WHERE id=?",
                (values["code"], values["name_en"], values["name_mr"], values["week_pattern"], values["day_of_week"], values["active"], _now(), row_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("MENU_CODE_ALREADY_EXISTS") from exc
        _audit(conn, user_id, "UPDATE", "MENU", row_id, values)
        return dict(conn.execute("SELECT * FROM menus WHERE id=?", (row_id,)).fetchone())


def _parse_iso_date(value: str, error_code: str) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except Exception as exc:
        raise ValueError(error_code) from exc


def _effective_recipe_row(conn: sqlite3.Connection, menu_id: str, ingredient_id: str, student_group: str, on_date: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM recipes
        WHERE menu_id=? AND ingredient_id=? AND student_group=? AND active=1
          AND effective_from<=?
          AND (effective_to IS NULL OR effective_to>=?)
        ORDER BY effective_from DESC, version DESC
        LIMIT 1
        """,
        (menu_id, ingredient_id, student_group, on_date, on_date),
    ).fetchone()


def get_recipe_standard(menu_id: str, on_date: str) -> dict[str, Any]:
    on_date = _parse_iso_date(on_date, "RECIPE_DATE_INVALID")
    runtime.init_db()
    with runtime.connect() as conn:
        menu = conn.execute("SELECT * FROM menus WHERE id=?", (menu_id,)).fetchone()
        if not menu:
            raise KeyError("MENU_NOT_FOUND")
        ingredients = conn.execute("SELECT * FROM ingredients WHERE active=1 ORDER BY name_en, code").fetchall()
        items: list[dict[str, Any]] = []
        for ingredient in ingredients:
            r15 = _effective_recipe_row(conn, menu_id, ingredient["id"], "CLASS_1_5", on_date)
            r68 = _effective_recipe_row(conn, menu_id, ingredient["id"], "CLASS_6_8", on_date)
            items.append(
                {
                    "ingredient_id": ingredient["id"],
                    "code": ingredient["code"],
                    "name_en": ingredient["name_en"],
                    "name_mr": ingredient["name_mr"],
                    "qty_class_1_5": float(r15["qty_per_student"]) if r15 else 0.0,
                    "qty_class_6_8": float(r68["qty_per_student"]) if r68 else 0.0,
                    "unit": (r15 or r68)["measurement_unit"] if (r15 or r68) else ingredient["base_unit"],
                }
            )
        return {
            "menu_id": menu_id,
            "menu_code": menu["code"],
            "menu_name_en": menu["name_en"],
            "menu_name_mr": menu["name_mr"],
            "on_date": on_date,
            "items": items,
        }


def save_recipe_standard(menu_id: str, data: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    effective_from = _parse_iso_date(str(data.get("effective_from") or ""), "RECIPE_EFFECTIVE_DATE_INVALID")
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("RECIPE_ITEMS_REQUIRED")

    runtime.init_db()
    with runtime.connect() as conn:
        if not conn.execute("SELECT id FROM menus WHERE id=?", (menu_id,)).fetchone():
            raise KeyError("MENU_NOT_FOUND")
        now = _now()
        saved = 0
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("RECIPE_ITEM_INVALID")
            ingredient_id = str(item.get("ingredient_id") or "").strip()
            ingredient = conn.execute("SELECT * FROM ingredients WHERE id=?", (ingredient_id,)).fetchone()
            if not ingredient:
                raise ValueError("INGREDIENT_NOT_FOUND")
            unit = str(item.get("unit") or ingredient["base_unit"]).strip().upper()
            if not unit:
                raise ValueError("RECIPE_UNIT_REQUIRED")
            quantities = {
                "CLASS_1_5": float(item.get("qty_class_1_5", 0) or 0),
                "CLASS_6_8": float(item.get("qty_class_6_8", 0) or 0),
            }
            if any(qty < 0 for qty in quantities.values()):
                raise ValueError("RECIPE_QUANTITY_INVALID")
            for group, qty in quantities.items():
                existing = conn.execute(
                    "SELECT id, version FROM recipes WHERE menu_id=? AND ingredient_id=? AND student_group=? AND effective_from=?",
                    (menu_id, ingredient_id, group, effective_from),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE recipes
                        SET qty_per_student=?, measurement_unit=?, active=1, updated_at=?
                        WHERE id=?
                        """,
                        (qty, unit, now, existing["id"]),
                    )
                    recipe_id = existing["id"]
                else:
                    previous = conn.execute(
                        "SELECT MAX(version) FROM recipes WHERE menu_id=? AND ingredient_id=? AND student_group=?",
                        (menu_id, ingredient_id, group),
                    ).fetchone()[0]
                    recipe_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO recipes
                            (id, menu_id, ingredient_id, student_group, qty_per_student, measurement_unit,
                             effective_from, effective_to, version, active, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 1, ?, ?)
                        """,
                        (recipe_id, menu_id, ingredient_id, group, qty, unit, effective_from, int(previous or 0) + 1, now, now),
                    )
                saved += 1
                _audit(
                    conn,
                    user_id,
                    "UPSERT",
                    "RECIPE",
                    recipe_id,
                    {"menu_id": menu_id, "ingredient_id": ingredient_id, "student_group": group, "effective_from": effective_from, "qty": qty, "unit": unit},
                )
        _audit(conn, user_id, "SAVE_STANDARD", "MENU_RECIPE_STANDARD", menu_id, {"effective_from": effective_from, "rows_saved": saved})
    return get_recipe_standard(menu_id, effective_from)
