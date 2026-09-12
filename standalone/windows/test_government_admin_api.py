from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-government-admin-test-"))
    os.environ["PMPOSHAN_DATA_DIR"] = str(temp_root)

    from fastapi.testclient import TestClient
    from bridge import app

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/setup/admin",
            json={
                "username": "system.admin",
                "password": "StrongSystemAdmin123!",
                "display_name": "System Admin",
            },
        )
        assert created.status_code == 200, created.text

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "system.admin", "password": "StrongSystemAdmin123!"},
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        before = client.get("/api/v1/admin/government-standard", headers=headers)
        assert before.status_code == 200, before.text
        assert before.json()["imported"] is False, before.text

        imported = client.post("/api/v1/admin/government-standard/import", headers=headers)
        assert imported.status_code == 200, imported.text
        body = imported.json()
        assert body["imported"] is True, body
        assert body["menus_standardized"] == 12, body
        assert body["government_recipe_rows"] == 102, body
        assert body["active_ingredients"] == 24, body
        assert body["active_menus"] == 12, body
        assert body["oil_inventory_unit"] == "KG", body
        assert body["norms"]["class_1_5"] == {
            "rice_g": 100,
            "pulse_g": 20,
            "vegetables_g": 50,
            "oil_g": 5,
        }, body
        assert body["norms"]["class_6_8"] == {
            "rice_g": 150,
            "pulse_g": 30,
            "vegetables_g": 75,
            "oil_g": 7.5,
        }, body
        backup = Path(body["backup_created"])
        assert backup.exists(), body

        second = client.post("/api/v1/admin/government-standard/import", headers=headers)
        assert second.status_code == 200, second.text
        assert second.json()["government_recipe_rows"] == 102, second.text
        assert Path(second.json()["backup_created"]).exists(), second.text

        status = client.get("/api/v1/admin/government-standard", headers=headers)
        assert status.status_code == 200, status.text
        current = status.json()
        assert current["imported"] is True, current
        assert current["source"]["gr_date"] == "2024-06-11", current
        assert current["government_recipe_rows"] == 102, current

        print(json.dumps({
            "ok": True,
            "phase": "5D-D-government-standard-admin",
            "admin_import_api": True,
            "automatic_backup": True,
            "idempotent_reimport": True,
            "active_ingredients": current["active_ingredients"],
            "active_menus": current["active_menus"],
            "government_recipe_rows": current["government_recipe_rows"],
            "oil_inventory_unit": current["oil_inventory_unit"],
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
