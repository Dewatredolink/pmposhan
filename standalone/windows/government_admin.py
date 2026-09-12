from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import government_standards
import runtime


def standard_status() -> dict[str, Any]:
    runtime.init_db()
    source = dict(government_standards.SOURCE)
    imported_metadata: dict[str, Any] | None = None

    with runtime.connect() as conn:
        metadata = conn.execute(
            "SELECT value, updated_at FROM app_metadata WHERE key='maharashtra_pm_poshan_standard'"
        ).fetchone()
        if metadata:
            try:
                imported_metadata = json.loads(str(metadata["value"]))
            except Exception:
                imported_metadata = {"raw": str(metadata["value"])}
            imported_metadata["updated_at"] = metadata["updated_at"]

        ingredient_count = int(conn.execute("SELECT COUNT(*) FROM ingredients WHERE active=1").fetchone()[0])
        menu_count = int(conn.execute("SELECT COUNT(*) FROM menus WHERE active=1").fetchone()[0])
        recipe_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM recipes WHERE active=1 AND effective_from=?",
                (source["effective_from"],),
            ).fetchone()[0]
        )
        oil = conn.execute("SELECT base_unit FROM ingredients WHERE code='OIL'").fetchone()
        oil_unit = str(oil["base_unit"]) if oil else None

        menu_codes = tuple(government_standards.MENU_COMPONENTS.keys())
        if menu_codes:
            placeholders = ",".join("?" for _ in menu_codes)
            standardized_menus = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM menus WHERE active=1 AND code IN ({placeholders})",
                    menu_codes,
                ).fetchone()[0]
            )
        else:
            standardized_menus = 0

    return {
        "ok": True,
        "imported": imported_metadata is not None and recipe_count > 0,
        "source": source,
        "imported_metadata": imported_metadata,
        "active_ingredients": ingredient_count,
        "active_menus": menu_count,
        "menus_standardized": standardized_menus,
        "government_recipe_rows": recipe_count,
        "oil_inventory_unit": oil_unit,
        "norms": {
            "class_1_5": {"rice_g": 100, "pulse_g": 20, "vegetables_g": 50, "oil_g": 5},
            "class_6_8": {"rice_g": 150, "pulse_g": 30, "vegetables_g": 75, "oil_g": 7.5},
        },
    }


def import_with_backup(actor_id: str) -> dict[str, Any]:
    backup = runtime.create_backup()
    result = government_standards.import_maharashtra_government_standards(actor_id)
    status = standard_status()
    return {
        **result,
        **status,
        "backup_created": str(Path(backup)),
    }
