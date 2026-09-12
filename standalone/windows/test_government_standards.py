from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-gov-standard-test-"))
    os.environ["PMPOSHAN_DATA_DIR"] = str(temp_root)

    import runtime
    import government_standards

    runtime.init_db()
    admin_id = runtime.create_first_admin("system.admin", "StrongSystemAdmin123!", "System Admin")
    result = government_standards.import_maharashtra_government_standards(admin_id)

    with runtime.connect() as conn:
        assert result["menus_standardized"] == 12, result
        assert result["norms"]["class_1_5"] == {"rice_g": 100, "pulse_g": 20, "vegetables_g": 50, "oil_g": 5}
        assert result["norms"]["class_6_8"] == {"rice_g": 150, "pulse_g": 30, "vegetables_g": 75, "oil_g": 7.5}
        assert conn.execute("SELECT base_unit FROM ingredients WHERE code='OIL'").fetchone()[0] == "KG"

        vpul = conn.execute("SELECT id FROM menus WHERE code='VPUL-W13-MON'").fetchone()[0]
        values = {
            r["code"]: (float(r["q15"]), float(r["q68"]), r["unit"])
            for r in conn.execute(
                """
                SELECT i.code,
                       MAX(CASE WHEN r.student_group='CLASS_1_5' THEN r.qty_per_student END) AS q15,
                       MAX(CASE WHEN r.student_group='CLASS_6_8' THEN r.qty_per_student END) AS q68,
                       MAX(r.measurement_unit) AS unit
                FROM recipes r JOIN ingredients i ON i.id=r.ingredient_id
                WHERE r.menu_id=? AND r.active=1 AND r.effective_from=?
                GROUP BY i.code
                """,
                (vpul, government_standards.SOURCE["effective_from"]),
            ).fetchall()
        }
        assert values["RICE"] == (0.1, 0.15, "KG"), values
        assert values["VATANA"] == (0.02, 0.03, "KG"), values
        assert values["VEGQTY"] == (0.05, 0.075, "KG"), values
        assert values["OIL"] == (0.005, 0.0075, "KG"), values

        mdvb = conn.execute("SELECT id FROM menus WHERE code='MDVB-W24-TUE'").fetchone()[0]
        split = {
            r["code"]: (float(r["q15"]), float(r["q68"]))
            for r in conn.execute(
                """
                SELECT i.code,
                       MAX(CASE WHEN r.student_group='CLASS_1_5' THEN r.qty_per_student END) AS q15,
                       MAX(CASE WHEN r.student_group='CLASS_6_8' THEN r.qty_per_student END) AS q68
                FROM recipes r JOIN ingredients i ON i.id=r.ingredient_id
                WHERE r.menu_id=? AND r.active=1 AND r.effective_from=?
                  AND i.code IN ('MOONG','TURDAL')
                GROUP BY i.code
                """,
                (mdvb, government_standards.SOURCE["effective_from"]),
            ).fetchall()
        }
        assert split["MOONG"] == (0.01, 0.015), split
        assert split["TURDAL"] == (0.01, 0.015), split

        metadata = conn.execute("SELECT value FROM app_metadata WHERE key='maharashtra_pm_poshan_standard'").fetchone()
        assert metadata is not None

    print(json.dumps({
        "ok": True,
        "source": government_standards.SOURCE,
        "menus_standardized": 12,
        "primary": "100g rice + 20g pulse + 50g vegetables + 5g oil",
        "upper_primary": "150g rice + 30g pulse + 75g vegetables + 7.5g oil",
        "moong_drumstick_split_verified": True,
        "oil_inventory_unit": "KG",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
