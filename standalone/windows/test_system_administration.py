from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-system-admin-test-"))
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
        admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        district = client.post(
            "/api/v1/master/districts",
            headers=admin_headers,
            json={"code": "PALGHAR", "name_en": "Palghar", "name_mr": "पालघर", "active": True},
        )
        assert district.status_code == 200, district.text
        block = client.post(
            "/api/v1/master/blocks",
            headers=admin_headers,
            json={"code": "MOKHADA", "district_id": district.json()["id"], "name_en": "Mokhada", "name_mr": "मोखाडा", "active": True},
        )
        assert block.status_code == 200, block.text
        cluster = client.post(
            "/api/v1/master/clusters",
            headers=admin_headers,
            json={"code": "GAYMUKH", "block_id": block.json()["id"], "name_en": "Gaymukh Cluster", "name_mr": "गायमुख केंद्र", "active": True},
        )
        assert cluster.status_code == 200, cluster.text
        school = client.post(
            "/api/v1/master/schools",
            headers=admin_headers,
            json={
                "code": "GAYMUKH001",
                "udise_code": "27360803502",
                "cluster_id": cluster.json()["id"],
                "name_en": "Gaymukhpada",
                "name_mr": "गायमुखपाडा",
                "village": "Gaymukhpada",
                "class_1_5_strength": 50,
                "class_6_8_strength": 20,
                "active": True,
            },
        )
        assert school.status_code == 200, school.text
        school_id = school.json()["id"]

        headmaster = client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "username": "headmaster.gaymukh",
                "display_name": "Headmaster Gaymukhpada",
                "password": "StrongHeadmaster123!",
                "role": "HEADMASTER",
                "school_ids": [school_id],
                "preferred_language": "mr",
            },
        )
        assert headmaster.status_code == 200, headmaster.text
        assert headmaster.json()["role"] == "HEADMASTER"
        assert headmaster.json()["school_ids"] == [school_id]

        users = client.get("/api/v1/admin/users", headers=admin_headers)
        assert users.status_code == 200, users.text
        assert {u["username"] for u in users.json()} == {"system.admin", "headmaster.gaymukh"}

        hm_login = client.post(
            "/api/v1/auth/login",
            json={"username": "headmaster.gaymukh", "password": "StrongHeadmaster123!"},
        )
        assert hm_login.status_code == 200, hm_login.text
        hm_headers = {"Authorization": f"Bearer {hm_login.json()['access_token']}"}
        hm_schools = client.get("/api/v1/schools", headers=hm_headers)
        assert hm_schools.status_code == 200, hm_schools.text
        assert [x["id"] for x in hm_schools.json()] == [school_id]

        restore = client.post("/api/v1/admin/restore-standard-masters", headers=admin_headers)
        assert restore.status_code == 200, restore.text
        body = restore.json()
        assert body["ingredients_total"] == 22, body
        assert body["menus_total"] == 12, body

        ingredients = client.get("/api/v1/master/ingredients", headers=admin_headers)
        menus = client.get("/api/v1/master/menus", headers=admin_headers)
        assert ingredients.status_code == 200, ingredients.text
        assert menus.status_code == 200, menus.text
        assert len(ingredients.json()) >= 22
        assert len(menus.json()) >= 12

        reset = client.post(
            f"/api/v1/admin/users/{headmaster.json()['id']}/reset-password",
            headers=admin_headers,
            json={"password": "ChangedHeadmaster123!"},
        )
        assert reset.status_code == 200, reset.text
        relogin = client.post(
            "/api/v1/auth/login",
            json={"username": "headmaster.gaymukh", "password": "ChangedHeadmaster123!"},
        )
        assert relogin.status_code == 200, relogin.text

        print(json.dumps({
            "ok": True,
            "phase": "5D-C-system-admin",
            "system_admin_user_management": True,
            "headmaster_creation": True,
            "school_scope": True,
            "password_reset": True,
            "standard_ingredients": 22,
            "standard_menus": 12,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
