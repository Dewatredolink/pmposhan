from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-school-profile-test-"))
    os.environ["PMPOSHAN_DATA_DIR"] = str(temp_root)

    from fastapi.testclient import TestClient
    from bridge import app

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/setup/admin",
            json={"username": "system.admin", "password": "StrongSystemAdmin123!", "display_name": "System Admin"},
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
                "name_en": "Z.P. School Gaymukhpada",
                "name_mr": "जि.प. शाळा गायमुखपाडा",
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
        teacher = client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "username": "teacher.gaymukh",
                "display_name": "Teacher Gaymukhpada",
                "password": "StrongTeacher123!",
                "role": "TEACHER",
                "school_ids": [school_id],
                "preferred_language": "en",
            },
        )
        assert teacher.status_code == 200, teacher.text

        empty_profile = client.get(f"/api/v1/school-profiles/{school_id}", headers=admin_headers)
        assert empty_profile.status_code == 200, empty_profile.text
        assert empty_profile.json()["profile"] is None
        assert {x["username"] for x in empty_profile.json()["assignments"]} == {"headmaster.gaymukh", "teacher.gaymukh"}

        saved = client.put(
            f"/api/v1/school-profiles/{school_id}",
            headers=admin_headers,
            json={
                "kitchen_type": "SCHOOL_KITCHEN",
                "cooking_agency": "School Management Committee",
                "headmaster_name": "Smt. Sheetal Shardarao Joshi",
                "meal_incharge_name": "Meal In-charge",
                "contact_mobile": "9876543210",
            },
        )
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["school"]["udise_code"] == "27360803502"
        assert body["profile"]["headmaster_name"] == "Smt. Sheetal Shardarao Joshi"
        assert body["profile"]["kitchen_type"] == "SCHOOL_KITCHEN"

        hm_login = client.post(
            "/api/v1/auth/login",
            json={"username": "headmaster.gaymukh", "password": "StrongHeadmaster123!"},
        )
        assert hm_login.status_code == 200, hm_login.text
        hm_headers = {"Authorization": f"Bearer {hm_login.json()['access_token']}"}
        hm_get = client.get(f"/api/v1/school-profiles/{school_id}", headers=hm_headers)
        assert hm_get.status_code == 200, hm_get.text
        hm_put = client.put(
            f"/api/v1/school-profiles/{school_id}",
            headers=hm_headers,
            json={
                "kitchen_type": "SCHOOL_KITCHEN",
                "cooking_agency": "School Management Committee",
                "headmaster_name": "Smt. Sheetal Shardarao Joshi",
                "meal_incharge_name": "Updated Meal In-charge",
                "contact_mobile": "9876543210",
            },
        )
        assert hm_put.status_code == 200, hm_put.text
        assert hm_put.json()["profile"]["meal_incharge_name"] == "Updated Meal In-charge"

        teacher_login = client.post(
            "/api/v1/auth/login",
            json={"username": "teacher.gaymukh", "password": "StrongTeacher123!"},
        )
        assert teacher_login.status_code == 200, teacher_login.text
        teacher_headers = {"Authorization": f"Bearer {teacher_login.json()['access_token']}"}
        teacher_get = client.get(f"/api/v1/school-profiles/{school_id}", headers=teacher_headers)
        assert teacher_get.status_code == 200, teacher_get.text
        teacher_put = client.put(
            f"/api/v1/school-profiles/{school_id}",
            headers=teacher_headers,
            json={"kitchen_type": "CENTRAL_KITCHEN"},
        )
        assert teacher_put.status_code == 403, teacher_put.text

        with __import__("runtime").connect() as conn:
            profile_count = int(conn.execute("SELECT COUNT(*) FROM school_profiles WHERE school_id=?", (school_id,)).fetchone()[0])
            audit_count = int(conn.execute("SELECT COUNT(*) FROM audit_log WHERE entity_type='SCHOOL_PROFILE'").fetchone()[0])
        assert profile_count == 1
        assert audit_count >= 2

        print(json.dumps({
            "ok": True,
            "phase": "5D-D-school-profile-parity",
            "school_profile_get": True,
            "school_profile_upsert": True,
            "assigned_users": 2,
            "headmaster_can_edit": True,
            "teacher_read_only": True,
            "audit_logged": True,
            "udise": "27360803502",
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
