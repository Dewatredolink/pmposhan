from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-phase5c2d-test-"))
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
    with runtime.connect() as conn:
        conn.execute(
            "INSERT INTO districts (id, code, name_en, name_mr) VALUES (?, ?, ?, ?)",
            (district_id, "PALGHAR", "Palghar", "पालघर"),
        )
        conn.execute(
            "INSERT INTO blocks (id, code, district_id, name_en, name_mr) VALUES (?, ?, ?, ?, ?)",
            (block_id, "MOKHADA", district_id, "Mokhada", "मोखाडा"),
        )
        conn.execute(
            "INSERT INTO clusters (id, code, block_id, name_en, name_mr) VALUES (?, ?, ?, ?, ?)",
            (cluster_id, "CL-01", block_id, "Cluster 1", "केंद्र १"),
        )
        conn.execute(
            """
            INSERT INTO schools
              (id, code, udise_code, cluster_id, name_en, name_mr, class_1_5_strength, class_6_8_strength)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (school_id, "SCH-001", "27360803502", cluster_id, "Gaymukhpada", "गायमुखपाडा", 40, 20),
        )
        conn.execute(
            """
            INSERT INTO ingredients
              (id, code, name_en, name_mr, category, base_unit, reorder_level, safety_stock, track_inventory, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
            """,
            (ingredient_id, "RICE", "Rice", "तांदूळ", "GRAIN", "KG", 12.0, 5.0),
        )

    with TestClient(app) as client:
        admin = client.post(
            "/api/v1/setup/admin",
            json={"username": "system.admin", "password": "StrongTestPassword123!", "display_name": "System Admin"},
        )
        assert admin.status_code == 200, admin.text
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "system.admin", "password": "StrongTestPassword123!"},
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        ingredients = client.get("/api/v1/ingredients", headers=headers)
        assert ingredients.status_code == 200, ingredients.text
        assert ingredients.json()[0]["id"] == ingredient_id

        opening = client.post(
            "/api/v1/stock/opening-balance",
            headers=headers,
            json={
                "school_id": school_id,
                "opening_date": "2026-09-01",
                "ingredient_id": ingredient_id,
                "quantity": 10,
                "remarks": "Initial stock",
            },
        )
        assert opening.status_code == 200, opening.text
        assert opening.json()["quantity"] == 10

        duplicate_opening = client.post(
            "/api/v1/stock/opening-balance",
            headers=headers,
            json={
                "school_id": school_id,
                "opening_date": "2026-09-01",
                "ingredient_id": ingredient_id,
                "quantity": 1,
            },
        )
        assert duplicate_opening.status_code == 400, duplicate_opening.text
        assert duplicate_opening.json()["detail"] == "OPENING_BALANCE_ALREADY_HAS_TRANSACTIONS"

        balance1 = client.get(f"/api/v1/stock/balances?school_id={school_id}", headers=headers)
        assert balance1.status_code == 200, balance1.text
        assert abs(balance1.json()[0]["balance"] - 10.0) < 1e-9
        assert balance1.json()[0]["low_stock"] is True

        receipt = client.post(
            "/api/v1/stock/receipts",
            headers=headers,
            json={
                "school_id": school_id,
                "receipt_date": "2026-09-02",
                "receipt_no": "CH-001",
                "source_name": "Supply Depot",
                "remarks": "Monthly supply",
                "lines": [{"ingredient_id": ingredient_id, "quantity": 5, "unit_cost": 25.5}],
            },
        )
        assert receipt.status_code == 200, receipt.text
        assert receipt.json()["lines"] == 1

        duplicate_receipt = client.post(
            "/api/v1/stock/receipts",
            headers=headers,
            json={
                "school_id": school_id,
                "receipt_date": "2026-09-02",
                "receipt_no": "CH-001",
                "lines": [{"ingredient_id": ingredient_id, "quantity": 1}],
            },
        )
        assert duplicate_receipt.status_code == 400, duplicate_receipt.text
        assert duplicate_receipt.json()["detail"] == "RECEIPT_NUMBER_ALREADY_EXISTS"

        receipt_list = client.get(f"/api/v1/stock/receipts?school_id={school_id}", headers=headers)
        assert receipt_list.status_code == 200, receipt_list.text
        assert receipt_list.json()[0]["receipt_no"] == "CH-001"
        assert receipt_list.json()[0]["lines"][0]["quantity"] == 5

        balance2 = client.get(f"/api/v1/stock/balances?school_id={school_id}", headers=headers)
        assert balance2.status_code == 200, balance2.text
        assert abs(balance2.json()[0]["balance"] - 15.0) < 1e-9
        assert balance2.json()[0]["low_stock"] is False

        adjustment = client.post(
            "/api/v1/stock/adjustments",
            headers=headers,
            json={
                "school_id": school_id,
                "adjustment_date": "2026-09-03",
                "adjustment_no": "ADJ-001",
                "ingredient_id": ingredient_id,
                "quantity": -3,
                "reason_code": "DAMAGE",
                "remarks": "Damaged stock",
            },
        )
        assert adjustment.status_code == 200, adjustment.text
        assert abs(adjustment.json()["balance_after"] - 12.0) < 1e-9

        negative_block = client.post(
            "/api/v1/stock/adjustments",
            headers=headers,
            json={
                "school_id": school_id,
                "adjustment_date": "2026-09-03",
                "adjustment_no": "ADJ-002",
                "ingredient_id": ingredient_id,
                "quantity": -20,
                "reason_code": "SHORTAGE",
            },
        )
        assert negative_block.status_code == 400, negative_block.text
        assert negative_block.json()["detail"] == "ADJUSTMENT_WOULD_CREATE_NEGATIVE_STOCK"

        adjustments = client.get(f"/api/v1/stock/adjustments?school_id={school_id}", headers=headers)
        assert adjustments.status_code == 200, adjustments.text
        assert adjustments.json()[0]["adjustment_no"] == "ADJ-001"

        physical = client.post(
            "/api/v1/stock/physical-verifications",
            headers=headers,
            json={
                "school_id": school_id,
                "verification_date": "2026-09-04",
                "verification_no": "PHY-001",
                "remarks": "Monthly physical count",
                "lines": [{"ingredient_id": ingredient_id, "physical_quantity": 11}],
            },
        )
        assert physical.status_code == 200, physical.text
        assert physical.json()["variance_lines"] == 1

        physical_list = client.get(f"/api/v1/stock/physical-verifications?school_id={school_id}", headers=headers)
        assert physical_list.status_code == 200, physical_list.text
        assert physical_list.json()[0]["verification_no"] == "PHY-001"
        line = physical_list.json()[0]["lines"][0]
        assert abs(line["system_quantity"] - 12.0) < 1e-9
        assert abs(line["physical_quantity"] - 11.0) < 1e-9
        assert abs(line["variance_quantity"] + 1.0) < 1e-9

        final_balance = client.get(f"/api/v1/stock/balances?school_id={school_id}", headers=headers)
        assert final_balance.status_code == 200, final_balance.text
        assert abs(final_balance.json()[0]["balance"] - 11.0) < 1e-9
        assert final_balance.json()[0]["low_stock"] is True

        ledger = client.get(
            f"/api/v1/stock/ledger?school_id={school_id}&ingredient_id={ingredient_id}",
            headers=headers,
        )
        assert ledger.status_code == 200, ledger.text
        types = {row["transaction_type"] for row in ledger.json()}
        assert {"OPENING", "RECEIPT", "ADJUSTMENT", "PHYSICAL_ADJUSTMENT"}.issubset(types)

        runtime.create_local_user("teacher.one", "StrongTeacherPassword123!", "TEACHER", "Teacher One")
        teacher_login = client.post(
            "/api/v1/auth/login",
            json={"username": "teacher.one", "password": "StrongTeacherPassword123!"},
        )
        assert teacher_login.status_code == 200, teacher_login.text
        teacher_headers = {"Authorization": f"Bearer {teacher_login.json()['access_token']}"}
        blocked_teacher_adjustment = client.post(
            "/api/v1/stock/adjustments",
            headers=teacher_headers,
            json={
                "school_id": school_id,
                "adjustment_date": "2026-09-05",
                "adjustment_no": "ADJ-TEACHER",
                "ingredient_id": ingredient_id,
                "quantity": 1,
                "reason_code": "CORRECTION",
            },
        )
        assert blocked_teacher_adjustment.status_code == 403, blocked_teacher_adjustment.text

        with runtime.connect() as conn:
            audit_count = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE entity_type IN ('OPENING_BALANCE','STOCK_RECEIPT','STOCK_ADJUSTMENT','PHYSICAL_STOCK_VERIFICATION')"
            ).fetchone()[0]
        assert audit_count >= 4

        print(
            "{\n"
            '  "ok": true,\n'
            '  "phase": "5C2-D",\n'
            '  "opening_balance": true,\n'
            '  "stock_receipts": true,\n'
            '  "stock_balances": true,\n'
            '  "low_stock": true,\n'
            '  "stock_ledger": true,\n'
            '  "stock_adjustments": true,\n'
            '  "negative_stock_block": true,\n'
            '  "physical_verification": true,\n'
            '  "role_authorization": true,\n'
            '  "audit_log": true\n'
            "}"
        )


if __name__ == "__main__":
    main()
