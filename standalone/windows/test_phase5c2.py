from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-phase5c2-test-"))
    os.environ["PMPOSHAN_DATA_DIR"] = str(temp_root)

    from fastapi.testclient import TestClient
    import runtime
    from bridge import app

    runtime.init_db()

    district_id = str(uuid.uuid4())
    block_id = str(uuid.uuid4())
    cluster_id = str(uuid.uuid4())
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
            (cluster_id, "SAMPLE-CLUSTER", block_id, "Sample Cluster", "नमुना केंद्र"),
        )

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
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        school = client.post(
            "/api/v1/schools",
            headers=headers,
            json={
                "code": "SCHOOL-001",
                "udise_code": "27360803502",
                "cluster_id": cluster_id,
                "name_en": "Gaymukhpada",
                "name_mr": "गायमुखपाडा",
                "village": "Gaymukhpada",
                "class_1_5_strength": 42,
                "class_6_8_strength": 18,
            },
        )
        assert school.status_code == 200, school.text
        school_body = school.json()
        school_id = school_body["id"]
        assert school_body["udise_code"] == "27360803502"
        assert school_body["district_name_en"] == "Palghar"
        assert school_body["block_name_en"] == "Mokhada"

        school_list = client.get("/api/v1/schools", headers=headers)
        assert school_list.status_code == 200, school_list.text
        assert len(school_list.json()) == 1

        duplicate_udise = client.post(
            "/api/v1/schools",
            headers=headers,
            json={
                "code": "SCHOOL-002",
                "udise_code": "27360803502",
                "cluster_id": cluster_id,
                "name_en": "Duplicate School",
                "name_mr": "दुबार शाळा",
            },
        )
        assert duplicate_udise.status_code == 400, duplicate_udise.text
        assert duplicate_udise.json()["detail"] == "SCHOOL_UDISE_ALREADY_EXISTS"

        updated = client.put(
            f"/api/v1/schools/{school_id}",
            headers=headers,
            json={"village": "Gaymukhpada Village", "class_1_5_strength": 45},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["village"] == "Gaymukhpada Village"
        assert updated.json()["class_1_5_strength"] == 45

        year1 = client.post(
            "/api/v1/academic-years",
            headers=headers,
            json={
                "code": "2026-27",
                "start_date": "2026-06-01",
                "end_date": "2027-05-31",
                "is_current": True,
            },
        )
        assert year1.status_code == 200, year1.text
        year1_id = year1.json()["id"]
        assert year1.json()["is_current"] == 1

        year2 = client.post(
            "/api/v1/academic-years",
            headers=headers,
            json={
                "code": "2027-28",
                "start_date": "2027-06-01",
                "end_date": "2028-05-31",
                "is_current": False,
            },
        )
        assert year2.status_code == 200, year2.text
        year2_id = year2.json()["id"]

        make_current = client.post(f"/api/v1/academic-years/{year2_id}/make-current", headers=headers)
        assert make_current.status_code == 200, make_current.text
        assert make_current.json()["is_current"] == 1

        years = client.get("/api/v1/academic-years", headers=headers)
        assert years.status_code == 200, years.text
        current = [row for row in years.json() if row["is_current"] == 1]
        assert len(current) == 1
        assert current[0]["id"] == year2_id
        old = next(row for row in years.json() if row["id"] == year1_id)
        assert old["is_current"] == 0

        invalid_dates = client.post(
            "/api/v1/academic-years",
            headers=headers,
            json={
                "code": "BAD-YEAR",
                "start_date": "2028-06-01",
                "end_date": "2028-05-31",
            },
        )
        assert invalid_dates.status_code == 400, invalid_dates.text
        assert invalid_dates.json()["detail"] == "ACADEMIC_YEAR_DATE_RANGE_INVALID"

        with runtime.connect() as conn:
            audit_count = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE entity_type IN ('SCHOOL','ACADEMIC_YEAR')"
            ).fetchone()[0]
        assert audit_count >= 5

        print(
            "{\n"
            '  "ok": true,\n'
            '  "phase": "5C2-A",\n'
            '  "school_profile_api": true,\n'
            '  "udise_uniqueness": true,\n'
            '  "hierarchy_validation": true,\n'
            '  "academic_year_api": true,\n'
            '  "single_current_year": true,\n'
            '  "audit_log": true\n'
            "}"
        )


if __name__ == "__main__":
    main()
