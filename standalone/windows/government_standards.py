from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

import admin_service
import runtime

SOURCE = {
    "authority": "Government of Maharashtra",
    "scheme": "PM POSHAN",
    "gr_number": "शापोआ-2022/प्र.क्र.117/एस.डी.3",
    "gr_date": "2024-06-11",
    "effective_from": "2024-06-11",
    "basis": "Per-child food norms and revised recipe schedule",
}

# Core PM POSHAN food norms per child per meal/day, represented in kilograms so
# recipe quantities and standalone stock ledger use one consistent mass unit.
CORE_NORMS_KG = {
    "CLASS_1_5": {"RICE": 0.100, "PULSE": 0.020, "VEGETABLES": 0.050, "OIL": 0.005},
    "CLASS_6_8": {"RICE": 0.150, "PULSE": 0.030, "VEGETABLES": 0.075, "OIL": 0.0075},
}

# Demo menu -> pulse/legume component in the Maharashtra recipe schedule.
# MDVB is the government moong + tur-dal split (10+10 g / 15+15 g).
MENU_COMPONENTS: dict[str, list[tuple[str, float, float]]] = {
    "VPUL-W13-MON": [("VATANA", 0.020, 0.030)],
    "MDKH-W13-TUE": [("MOONGDAL", 0.020, 0.030)],
    "CHPUL-W13-WED": [("HARBHARA", 0.020, 0.030), ("RICEFLOUR", 0.020, 0.015)],
    "MBHAT-W13-THU": [("VATANA", 0.020, 0.030)],
    "CHKH-W13-FRI": [("CHAWLI", 0.020, 0.030)],
    "MUSAL-W13-SAT": [("MATKI", 0.020, 0.030)],
    "MTPUL-W24-MON": [("VATANA", 0.020, 0.030)],
    "MDVB-W24-TUE": [("MOONG", 0.010, 0.015), ("TURDAL", 0.010, 0.015)],
    "SOYP-W24-WED": [("SOYA", 0.020, 0.030)],
    "VPUL-W24-THU": [("VATANA", 0.020, 0.030)],
    "MDKH-W24-FRI": [("MOONGDAL", 0.020, 0.030)],
    "MASP-W24-SAT": [("MASOORDAL", 0.020, 0.030), ("SUGAR", 0.006, 0.009)],
}

EXTRA_INGREDIENTS = [
    ("VEGQTY", "Vegetables", "भाजीपाला", "VEGETABLE", "KG", False),
    ("RICEFLOUR", "Rice Flour", "तांदळाचे पीठ", "CEREAL_PULSE", "KG", True),
]


def _now() -> str:
    return runtime.utc_now()


def _audit(conn: sqlite3.Connection, actor_id: str | None, action: str, entity_type: str, entity_id: str, details: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (id, occurred_at, user_id, action, entity_type, entity_id, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), _now(), actor_id, action, entity_type, entity_id, json.dumps(details, ensure_ascii=False, sort_keys=True)),
    )


def _ensure_extra_ingredient(conn: sqlite3.Connection, row: tuple[str, str, str, str, str, bool], now: str) -> str:
    code, name_en, name_mr, category, unit, track = row
    existing = conn.execute("SELECT id FROM ingredients WHERE code=?", (code,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE ingredients SET name_en=?, name_mr=?, category=?, base_unit=?, track_inventory=?, active=1, updated_at=? WHERE code=?",
            (name_en, name_mr, category, unit, 1 if track else 0, now, code),
        )
        return str(existing["id"])
    ingredient_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO ingredients
            (id, code, name_en, name_mr, category, base_unit, reorder_level, safety_stock,
             track_inventory, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, 1, ?, ?)
        """,
        (ingredient_id, code, name_en, name_mr, category, unit, 1 if track else 0, now, now),
    )
    return ingredient_id


def _upsert_recipe(conn: sqlite3.Connection, menu_id: str, ingredient_id: str, group: str, qty: float, now: str) -> None:
    effective_from = SOURCE["effective_from"]
    existing = conn.execute(
        "SELECT id FROM recipes WHERE menu_id=? AND ingredient_id=? AND student_group=? AND effective_from=?",
        (menu_id, ingredient_id, group, effective_from),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE recipes SET qty_per_student=?, measurement_unit='KG', active=1, updated_at=? WHERE id=?",
            (qty, now, existing["id"]),
        )
        return
    previous = conn.execute(
        "SELECT MAX(version) FROM recipes WHERE menu_id=? AND ingredient_id=? AND student_group=?",
        (menu_id, ingredient_id, group),
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO recipes
            (id, menu_id, ingredient_id, student_group, qty_per_student, measurement_unit,
             effective_from, effective_to, version, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'KG', ?, NULL, ?, 1, ?, ?)
        """,
        (str(uuid.uuid4()), menu_id, ingredient_id, group, qty, effective_from, int(previous or 0) + 1, now, now),
    )


def import_maharashtra_government_standards(actor_id: str) -> dict[str, Any]:
    """Import the Maharashtra PM POSHAN per-student norms into standalone recipes.

    The importer is idempotent. It preserves later recipe versions by using the
    GR effective date (2024-06-11). It also refuses to reinterpret existing oil
    stock from litres to kilograms; the oil unit is changed to KG only when the
    installation has no oil stock transactions yet.
    """
    runtime.init_db()
    admin_service.restore_standard_masters(actor_id)
    now = _now()

    with runtime.connect() as conn:
        oil = conn.execute("SELECT id, base_unit FROM ingredients WHERE code='OIL'").fetchone()
        if not oil:
            raise ValueError("OIL_MASTER_NOT_FOUND")
        oil_tx = int(conn.execute("SELECT COUNT(*) FROM stock_transactions WHERE ingredient_id=?", (oil["id"],)).fetchone()[0])
        if str(oil["base_unit"]).upper() != "KG":
            if oil_tx:
                raise ValueError("OIL_UNIT_MIGRATION_BLOCKED_EXISTING_STOCK_TRANSACTIONS")
            conn.execute("UPDATE ingredients SET base_unit='KG', name_en='Cooking Oil', name_mr='खाद्यतेल', updated_at=? WHERE id=?", (now, oil["id"]))

        for row in EXTRA_INGREDIENTS:
            _ensure_extra_ingredient(conn, row, now)

        ingredient_ids = {str(r["code"]): str(r["id"]) for r in conn.execute("SELECT id, code FROM ingredients").fetchall()}
        menu_rows = {str(r["code"]): str(r["id"]) for r in conn.execute("SELECT id, code FROM menus").fetchall()}

        required_codes = {"RICE", "OIL", "VEGQTY"}
        for components in MENU_COMPONENTS.values():
            required_codes.update(code for code, _, _ in components)
        missing_ingredients = sorted(code for code in required_codes if code not in ingredient_ids)
        missing_menus = sorted(code for code in MENU_COMPONENTS if code not in menu_rows)
        if missing_ingredients:
            raise ValueError("STANDARD_INGREDIENTS_MISSING:" + ",".join(missing_ingredients))
        if missing_menus:
            raise ValueError("STANDARD_MENUS_MISSING:" + ",".join(missing_menus))

        recipe_rows = 0
        for menu_code, components in MENU_COMPONENTS.items():
            menu_id = menu_rows[menu_code]
            common = [
                ("RICE", 0.100, 0.150),
                ("OIL", 0.005, 0.0075),
                ("VEGQTY", 0.050, 0.075),
            ]
            for ingredient_code, q15, q68 in common + components:
                ingredient_id = ingredient_ids[ingredient_code]
                _upsert_recipe(conn, menu_id, ingredient_id, "CLASS_1_5", q15, now)
                _upsert_recipe(conn, menu_id, ingredient_id, "CLASS_6_8", q68, now)
                recipe_rows += 2

        conn.execute(
            """
            INSERT INTO app_metadata (key, value, updated_at)
            VALUES ('maharashtra_pm_poshan_standard', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (json.dumps(SOURCE, ensure_ascii=False, sort_keys=True), now),
        )
        _audit(
            conn,
            actor_id,
            "IMPORT_GOVERNMENT_STANDARDS",
            "PM_POSHAN_RECIPE_STANDARD",
            SOURCE["gr_number"],
            {"source": SOURCE, "menus": len(MENU_COMPONENTS), "recipe_rows": recipe_rows},
        )

    return {
        "ok": True,
        "source": SOURCE,
        "menus_standardized": len(MENU_COMPONENTS),
        "recipe_rows_upserted": recipe_rows,
        "norms": {
            "class_1_5": {"rice_g": 100, "pulse_g": 20, "vegetables_g": 50, "oil_g": 5},
            "class_6_8": {"rice_g": 150, "pulse_g": 30, "vegetables_g": 75, "oil_g": 7.5},
        },
    }
