from __future__ import annotations

import json
import os
from pathlib import Path


def _configure_real_data_dir() -> Path:
    configured = (os.environ.get("PMPOSHAN_DATA_DIR") or "").strip()
    if configured:
        return Path(configured)
    local_app_data = (os.environ.get("LOCALAPPDATA") or "").strip()
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA_NOT_AVAILABLE")
    target = Path(local_app_data) / "PMPoshan"
    os.environ["PMPOSHAN_DATA_DIR"] = str(target)
    return target


def main() -> None:
    data_dir = _configure_real_data_dir()

    import runtime
    import government_standards

    runtime.init_db()
    with runtime.connect() as conn:
        actor = conn.execute(
            "SELECT id, username FROM local_users WHERE role='SYSTEM_ADMIN' AND active=1 ORDER BY created_at LIMIT 1"
        ).fetchone()
        if not actor:
            raise RuntimeError("ACTIVE_SYSTEM_ADMIN_NOT_FOUND")

    backup = runtime.create_backup()
    result = government_standards.import_maharashtra_government_standards(str(actor["id"]))

    with runtime.connect() as conn:
        ingredient_count = int(conn.execute("SELECT COUNT(*) FROM ingredients WHERE active=1").fetchone()[0])
        menu_count = int(conn.execute("SELECT COUNT(*) FROM menus WHERE active=1").fetchone()[0])
        recipe_count = int(conn.execute(
            "SELECT COUNT(*) FROM recipes WHERE active=1 AND effective_from=?",
            (government_standards.SOURCE["effective_from"],),
        ).fetchone()[0])
        oil_unit = conn.execute("SELECT base_unit FROM ingredients WHERE code='OIL'").fetchone()[0]

    print(json.dumps({
        **result,
        "data_dir": str(data_dir),
        "backup_created": str(backup),
        "active_ingredients": ingredient_count,
        "active_menus": menu_count,
        "government_recipe_rows": recipe_count,
        "oil_inventory_unit": oil_unit,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
