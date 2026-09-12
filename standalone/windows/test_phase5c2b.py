from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-phase5c2b-test-"))
    os.environ["PMPOSHAN_DATA_DIR"] = str(temp_root)

    from fastapi.testclient import TestClient
    import runtime
    from bridge import app

    runtime.init_db()

    with TestClient(app) as client:
        created_admin = client.post(
            "/api/v1/setup/admin",
            json={
                "username": "system.admin",
                "password": "StrongTestPassword123!",
                "display_name": "System Admin",
            },
        )
        assert created_admin.status_code == 200, created_admin.text

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "system.admin", "password": "StrongTestPassword123!"},
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        district = client.post(
            "/api/v1/master/districts",
            headers=headers,
            json={"code": "PALGHAR", "name_en": "Palghar", "name_mr": "पालघर", "active": True},
        )
        assert district.status_code == 200, district.text
        district_id = district.json()["id"]

        block = client.post(
            "/api/v1/master/blocks",
            headers=headers,
            json={"code": "MOKHADA", "district_id": district_id, "name_en": "Mokhada", "name_mr": "मोखाडा", "active": True},
        )
        assert block.status_code == 200, block.text
        block_id = block.json()["id"]

        cluster = client.post(
            "/api/v1/master/clusters",
            headers=headers,
            json={"code": "GM-CLUSTER", "block_id": block_id, "name_en": "Gaymukhpada Cluster", "name_mr": "गायमुखपाडा केंद्र", "active": True},
        )
        assert cluster.status_code == 200, cluster.text
        cluster_id = cluster.json()["id"]

        school = client.post(
            "/api/v1/master/schools",
            headers=headers,
            json={
                "code": "SCHOOL-001",
                "udise_code": "27360803502",
                "cluster_id": cluster_id,
                "name_en": "Gaymukhpada",
                "name_mr": "गायमुखपाडा",
                "class_1_5_strength": 45,
                "class_6_8_strength": 18,
                "active": True,
            },
        )
        assert school.status_code == 200, school.text

        for endpoint in ("districts", "blocks", "clusters", "schools"):
            response = client.get(f"/api/v1/master/{endpoint}", headers=headers)
            assert response.status_code == 200, response.text
            assert len(response.json()) == 1, response.text

        ingredient = client.post(
            "/api/v1/master/ingredients",
            headers=headers,
            json={
                "code": "RICE",
                "name_en": "Rice",
                "name_mr": "तांदूळ",
                "category": "GRAIN",
                "base_unit": "KG",
                "reorder_level": 10,
                "safety_stock": 5,
                "track_inventory": True,
                "active": True,
            },
        )
        assert ingredient.status_code == 200, ingredient.text
        ingredient_id = ingredient.json()["id"]

        duplicate = client.post(
            "/api/v1/master/ingredients",
            headers=headers,
            json={
                "code": "RICE",
                "name_en": "Rice Duplicate",
                "name_mr": "तांदूळ",
                "category": "GRAIN",
                "base_unit": "KG",
            },
        )
        assert duplicate.status_code == 400, duplicate.text
        assert duplicate.json()["detail"] == "INGREDIENT_CODE_ALREADY_EXISTS"

        ingredient_update = client.put(
            f"/api/v1/master/ingredients/{ingredient_id}",
            headers=headers,
            json={
                "code": "RICE",
                "name_en": "Rice",
                "name_mr": "तांदूळ",
                "category": "GRAIN",
                "base_unit": "KG",
                "reorder_level": 12.5,
                "safety_stock": 6,
                "track_inventory": True,
                "active": True,
            },
        )
        assert ingredient_update.status_code == 200, ingredient_update.text
        assert float(ingredient_update.json()["reorder_level"]) == 12.5

        menu = client.post(
            "/api/v1/master/menus",
            headers=headers,
            json={
                "code": "MON-RICE",
                "name_en": "Monday Rice Meal",
                "name_mr": "सोमवार तांदूळ आहार",
                "week_pattern": "CUSTOM",
                "day_of_week": 1,
                "active": True,
            },
        )
        assert menu.status_code == 200, menu.text
        menu_id = menu.json()["id"]

        invalid_menu = client.post(
            "/api/v1/master/menus",
            headers=headers,
            json={
                "code": "BAD-DAY",
                "name_en": "Bad Day",
                "name_mr": "चुकीचा वार",
                "week_pattern": "CUSTOM",
                "day_of_week": 7,
            },
        )
        assert invalid_menu.status_code == 400, invalid_menu.text
        assert invalid_menu.json()["detail"] == "MENU_DAY_INVALID"

        blank_standard = client.get(
            f"/api/v1/master/menus/{menu_id}/recipe-standard?on_date=2026-09-01",
            headers=headers,
        )
        assert blank_standard.status_code == 200, blank_standard.text
        blank_items = blank_standard.json()["items"]
        assert len(blank_items) == 1
        assert blank_items[0]["ingredient_id"] == ingredient_id
        assert float(blank_items[0]["qty_class_1_5"]) == 0
        assert float(blank_items[0]["qty_class_6_8"]) == 0
        assert blank_items[0]["unit"] == "KG"

        save_v1 = client.put(
            f"/api/v1/master/menus/{menu_id}/recipe-standard",
            headers=headers,
            json={
                "effective_from": "2026-09-01",
                "items": [
                    {
                        "ingredient_id": ingredient_id,
                        "qty_class_1_5": 0.10,
                        "qty_class_6_8": 0.15,
                        "unit": "KG",
                    }
                ],
            },
        )
        assert save_v1.status_code == 200, save_v1.text
        assert abs(float(save_v1.json()["items"][0]["qty_class_1_5"]) - 0.10) < 1e-9
        assert abs(float(save_v1.json()["items"][0]["qty_class_6_8"]) - 0.15) < 1e-9

        save_v2 = client.put(
            f"/api/v1/master/menus/{menu_id}/recipe-standard",
            headers=headers,
            json={
                "effective_from": "2026-10-01",
                "items": [
                    {
                        "ingredient_id": ingredient_id,
                        "qty_class_1_5": 0.11,
                        "qty_class_6_8": 0.16,
                        "unit": "KG",
                    }
                ],
            },
        )
        assert save_v2.status_code == 200, save_v2.text

        historical = client.get(
            f"/api/v1/master/menus/{menu_id}/recipe-standard?on_date=2026-09-15",
            headers=headers,
        )
        assert historical.status_code == 200, historical.text
        assert abs(float(historical.json()["items"][0]["qty_class_1_5"]) - 0.10) < 1e-9

        current = client.get(
            f"/api/v1/master/menus/{menu_id}/recipe-standard?on_date=2026-10-15",
            headers=headers,
        )
        assert current.status_code == 200, current.text
        assert abs(float(current.json()["items"][0]["qty_class_1_5"]) - 0.11) < 1e-9
        assert abs(float(current.json()["items"][0]["qty_class_6_8"]) - 0.16) < 1e-9

        unauthenticated = client.get("/api/v1/master/menus")
        assert unauthenticated.status_code == 401, unauthenticated.text

        with runtime.connect() as conn:
            recipe_rows = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
            audit_rows = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE entity_type IN ('INGREDIENT','MENU','RECIPE','MENU_RECIPE_STANDARD')"
            ).fetchone()[0]
        assert recipe_rows == 4
        assert audit_rows >= 8

        print(
            "{\n"
            '  "ok": true,\n'
            '  "phase": "5C2-B",\n'
            '  "master_hierarchy_compatibility": true,\n'
            '  "ingredient_master": true,\n'
            '  "menu_master": true,\n'
            '  "recipe_standard": true,\n'
            '  "effective_dated_recipes": true,\n'
            '  "authorization": true,\n'
            '  "audit_log": true\n'
            "}"
        )


if __name__ == "__main__":
    main()
