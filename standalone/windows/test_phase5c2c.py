from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-phase5c2c-test-"))
    os.environ["PMPOSHAN_DATA_DIR"] = str(temp_root)

    from fastapi.testclient import TestClient
    import runtime
    from bridge import app

    runtime.init_db()

    district_id = str(uuid.uuid4())
    block_id = str(uuid.uuid4())
    cluster_id = str(uuid.uuid4())
    school_id = str(uuid.uuid4())
    ingredient_id = str(uuid.uuid4())
    menu_id = str(uuid.uuid4())
    meal_date = "2026-09-14"

    with runtime.connect() as conn:
        conn.execute("INSERT INTO districts (id, code, name_en, name_mr) VALUES (?, 'PAL', 'Palghar', 'पालघर')", (district_id,))
        conn.execute("INSERT INTO blocks (id, code, district_id, name_en, name_mr) VALUES (?, 'MOK', ?, 'Mokhada', 'मोखाडा')", (block_id, district_id))
        conn.execute("INSERT INTO clusters (id, code, block_id, name_en, name_mr) VALUES (?, 'CLU', ?, 'Cluster', 'केंद्र')", (cluster_id, block_id))
        conn.execute(
            """
            INSERT INTO schools
                (id, code, udise_code, cluster_id, name_en, name_mr, class_1_5_strength, class_6_8_strength)
            VALUES (?, 'SCH', '27360803502', ?, 'Gaymukhpada', 'गायमुखपाडा', 50, 20)
            """,
            (school_id, cluster_id),
        )
        conn.execute(
            """
            INSERT INTO ingredients
                (id, code, name_en, name_mr, category, base_unit, reorder_level, safety_stock, track_inventory, active)
            VALUES (?, 'RICE', 'Rice', 'तांदूळ', 'GRAIN', 'KG', 2, 1, 1, 1)
            """,
            (ingredient_id,),
        )
        conn.execute(
            "INSERT INTO menus (id, code, name_en, name_mr, week_pattern, day_of_week, active) VALUES (?, 'MON-RICE', 'Rice Meal', 'भात', 'CUSTOM', 1, 1)",
            (menu_id,),
        )
        conn.execute(
            """
            INSERT INTO recipes
                (id, menu_id, ingredient_id, student_group, qty_per_student, measurement_unit, effective_from, version, active)
            VALUES (?, ?, ?, 'CLASS_1_5', 0.10, 'KG', '2026-06-01', 1, 1)
            """,
            (str(uuid.uuid4()), menu_id, ingredient_id),
        )
        conn.execute(
            """
            INSERT INTO recipes
                (id, menu_id, ingredient_id, student_group, qty_per_student, measurement_unit, effective_from, version, active)
            VALUES (?, ?, ?, 'CLASS_6_8', 0.15, 'KG', '2026-06-01', 1, 1)
            """,
            (str(uuid.uuid4()), menu_id, ingredient_id),
        )
        conn.execute(
            "INSERT INTO menu_schedules (id, school_id, menu_date, menu_id, active) VALUES (?, ?, ?, ?, 1)",
            (str(uuid.uuid4()), school_id, meal_date, menu_id),
        )

    with TestClient(app) as client:
        created_admin = client.post(
            "/api/v1/setup/admin",
            json={"username": "system.admin", "password": "StrongTestPassword123!", "display_name": "System Admin"},
        )
        assert created_admin.status_code == 200, created_admin.text

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "system.admin", "password": "StrongTestPassword123!"},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        menus = client.get("/api/v1/menus", headers=headers)
        assert menus.status_code == 200, menus.text
        assert menus.json()[0]["id"] == menu_id

        preview = client.get(
            f"/api/v1/menus/{menu_id}/recipe-preview?on_date={meal_date}&class_1_5=40&class_6_8=10",
            headers=headers,
        )
        assert preview.status_code == 200, preview.text
        assert len(preview.json()["items"]) == 1
        assert abs(preview.json()["items"][0]["required_total"] - 5.5) < 1e-9

        initial = client.get(f"/api/v1/daily-operations?school_id={school_id}&meal_date={meal_date}", headers=headers)
        assert initial.status_code == 200, initial.text
        assert initial.json()["planned_menu"]["menu_id"] == menu_id
        assert initial.json()["attendance"] is None

        attendance = client.put(
            "/api/v1/daily-attendance",
            headers=headers,
            json={
                "school_id": school_id,
                "meal_date": meal_date,
                "class_1_5_enrolled": 50,
                "class_1_5_present": 40,
                "class_6_8_enrolled": 20,
                "class_6_8_present": 10,
                "status": "SUBMITTED",
            },
        )
        assert attendance.status_code == 200, attendance.text
        assert attendance.json()["status"] == "SUBMITTED"

        meal = client.put(
            "/api/v1/daily-meal",
            headers=headers,
            json={
                "school_id": school_id,
                "meal_date": meal_date,
                "menu_id": menu_id,
                "meals_class_1_5": 40,
                "meals_class_6_8": 10,
                "tasting_done": True,
                "hygiene_ok": True,
                "remarks": "OK",
                "status": "SUBMITTED",
            },
        )
        assert meal.status_code == 200, meal.text
        meal_id = meal.json()["id"]

        blocked = client.post(
            "/api/v1/daily-operations/verify",
            headers=headers,
            json={"school_id": school_id, "meal_date": meal_date},
        )
        assert blocked.status_code == 400, blocked.text
        assert blocked.json()["detail"].startswith("INSUFFICIENT_STOCK:")

        admin_id = login.json()["user"]["id"]
        with runtime.connect() as conn:
            conn.execute(
                """
                INSERT INTO stock_transactions
                    (id, school_id, ingredient_id, transaction_date, transaction_type, quantity,
                     reference_type, reference_id, reference_no, entered_by_user_id, entered_by_username)
                VALUES (?, ?, ?, '2026-09-13', 'RECEIPT', 10.0, 'TEST_RECEIPT', ?, 'TEST-001', ?, 'system.admin')
                """,
                (str(uuid.uuid4()), school_id, ingredient_id, str(uuid.uuid4()), admin_id),
            )

        verified = client.post(
            "/api/v1/daily-operations/verify",
            headers=headers,
            json={"school_id": school_id, "meal_date": meal_date},
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["verified"] is True
        assert verified.json()["stock_consumption_transactions"] == 1

        final = client.get(f"/api/v1/daily-operations?school_id={school_id}&meal_date={meal_date}", headers=headers)
        assert final.status_code == 200, final.text
        assert final.json()["attendance"]["status"] == "VERIFIED"
        assert final.json()["meal"]["status"] == "VERIFIED"

        with runtime.connect() as conn:
            consumption = conn.execute(
                "SELECT quantity FROM stock_transactions WHERE reference_type='DAILY_MEAL' AND reference_id=? AND transaction_type='CONSUMPTION'",
                (meal_id,),
            ).fetchone()
            assert consumption is not None
            assert abs(float(consumption["quantity"]) + 5.5) < 1e-9
            balance = float(conn.execute("SELECT COALESCE(SUM(quantity),0) FROM stock_transactions WHERE school_id=? AND ingredient_id=?", (school_id, ingredient_id)).fetchone()[0])
            assert abs(balance - 4.5) < 1e-9

        second_verify = client.post(
            "/api/v1/daily-operations/verify",
            headers=headers,
            json={"school_id": school_id, "meal_date": meal_date},
        )
        assert second_verify.status_code == 200, second_verify.text
        assert second_verify.json()["already_verified"] is True
        assert second_verify.json()["stock_consumption_transactions"] == 1

        locked_edit = client.put(
            "/api/v1/daily-meal",
            headers=headers,
            json={
                "school_id": school_id,
                "meal_date": meal_date,
                "menu_id": menu_id,
                "meals_class_1_5": 39,
                "meals_class_6_8": 10,
                "tasting_done": True,
                "hygiene_ok": True,
                "status": "DRAFT",
            },
        )
        assert locked_edit.status_code == 400, locked_edit.text
        assert locked_edit.json()["detail"] == "MEAL_ALREADY_VERIFIED"

        with runtime.connect() as conn:
            audit_count = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE entity_type IN ('DAILY_ATTENDANCE','DAILY_MEAL','DAILY_OPERATIONS')"
            ).fetchone()[0]
        assert audit_count >= 3

        print(
            "{\n"
            '  "ok": true,\n'
            '  "phase": "5C2-C",\n'
            '  "daily_attendance": true,\n'
            '  "daily_meal": true,\n'
            '  "planned_menu": true,\n'
            '  "recipe_preview": true,\n'
            '  "insufficient_stock_block": true,\n'
            '  "automatic_consumption": true,\n'
            '  "verification_idempotent": true,\n'
            '  "verified_records_locked": true,\n'
            '  "audit_log": true\n'
            "}"
        )


if __name__ == "__main__":
    main()
