from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="pmposhan-phase5c2f-test-"))
    os.environ["PMPOSHAN_DATA_DIR"] = str(root)

    from fastapi.testclient import TestClient
    import runtime
    from bridge import app

    runtime.init_db()
    admin_id = runtime.create_first_admin("system.admin", "StrongTestPassword123!", "System Admin")

    district_id, block_id, cluster_id, school_id, menu_id = [str(uuid.uuid4()) for _ in range(5)]
    now = runtime.utc_now()
    with runtime.connect() as conn:
        conn.execute("INSERT INTO districts (id,code,name_en,name_mr,active,created_at,updated_at) VALUES (?,?,?,?,1,?,?)", (district_id,"D1","District","जिल्हा",now,now))
        conn.execute("INSERT INTO blocks (id,code,district_id,name_en,name_mr,active,created_at,updated_at) VALUES (?,?,?,?,?,1,?,?)", (block_id,"B1",district_id,"Block","तालुका",now,now))
        conn.execute("INSERT INTO clusters (id,code,block_id,name_en,name_mr,active,created_at,updated_at) VALUES (?,?,?,?,?,1,?,?)", (cluster_id,"C1",block_id,"Cluster","केंद्र",now,now))
        conn.execute("INSERT INTO schools (id,code,udise_code,cluster_id,name_en,name_mr,village,class_1_5_strength,class_6_8_strength,active,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,1,?,?)", (school_id,"S1","27360803502",cluster_id,"Test School","चाचणी शाळा","Village",100,50,now,now))
        conn.execute("INSERT INTO menus (id,code,name_en,name_mr,week_pattern,day_of_week,active,created_at,updated_at) VALUES (?,?,?,?,?,?,1,?,?)", (menu_id,"M1","Menu","मेनू","WEEKLY",1,now,now))

        # One complete verified day.
        conn.execute("""INSERT INTO daily_attendance (id,school_id,meal_date,class_1_5_enrolled,class_1_5_present,class_6_8_enrolled,class_6_8_present,status,entered_by_user_id,entered_by_username,verified_by_user_id,verified_by_username,verified_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'VERIFIED',?,?,?,?,?,?,?)""", (str(uuid.uuid4()),school_id,"2026-09-01",100,90,50,45,admin_id,"system.admin",admin_id,"system.admin",now,now,now))
        conn.execute("""INSERT INTO daily_meal_entries (id,school_id,meal_date,menu_id,meals_class_1_5,meals_class_6_8,total_meals,tasting_done,hygiene_ok,status,entered_by_user_id,entered_by_username,verified_by_user_id,verified_by_username,verified_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,1,1,'VERIFIED',?,?,?,?,?,?,?)""", (str(uuid.uuid4()),school_id,"2026-09-01",menu_id,90,45,135,admin_id,"system.admin",admin_id,"system.admin",now,now,now))

        # One recorded but incomplete day to test exception aggregation.
        conn.execute("""INSERT INTO daily_attendance (id,school_id,meal_date,class_1_5_enrolled,class_1_5_present,class_6_8_enrolled,class_6_8_present,status,entered_by_user_id,entered_by_username,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'DRAFT',?,?,?,?)""", (str(uuid.uuid4()),school_id,"2026-09-02",100,88,50,44,admin_id,"system.admin",now,now))

    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={"username":"system.admin","password":"StrongTestPassword123!"})
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        scope = client.get("/api/v1/hierarchy/scope", headers=headers)
        assert scope.status_code == 200, scope.text
        schools = scope.json()["schools"]
        assert len(schools) == 1 and schools[0]["school_id"] == school_id
        assert schools[0]["district_name_en"] == "District"

        before = client.get("/api/v1/monthly-returns/summary?year=2026&month=9", headers=headers)
        assert before.status_code == 200, before.text
        assert before.json()["missing_returns"] == 1

        generated = client.post("/api/v1/monthly-returns/generate", headers=headers, json={"school_id":school_id,"year":2026,"month":9})
        assert generated.status_code == 200, generated.text
        g = generated.json()
        return_id = g["id"]
        assert g["status"] == "DRAFT"
        assert g["recorded_days"] == 2 and g["verified_days"] == 1 and g["incomplete_days"] == 1
        assert g["attendance_class_1_5"] == 90 and g["attendance_class_6_8"] == 45
        assert g["meals_class_1_5"] == 90 and g["meals_class_6_8"] == 45 and g["total_meals"] == 135

        after = client.get("/api/v1/monthly-returns/summary?year=2026&month=9", headers=headers)
        assert after.status_code == 200, after.text
        s = after.json()
        assert s["returns_generated"] == 1 and s["missing_returns"] == 0 and s["exception_returns"] == 1

        submitted = client.post(f"/api/v1/monthly-returns/{return_id}/submit", headers=headers, json={"remarks":None})
        assert submitted.status_code == 200 and submitted.json()["status"] == "SUBMITTED", submitted.text

        returned = client.post(f"/api/v1/monthly-returns/{return_id}/return", headers=headers, json={"remarks":"Correct incomplete daily entry"})
        assert returned.status_code == 200 and returned.json()["status"] == "RETURNED", returned.text
        assert returned.json()["return_reason"] == "Correct incomplete daily entry"

        refreshed = client.post("/api/v1/monthly-returns/generate", headers=headers, json={"school_id":school_id,"year":2026,"month":9})
        assert refreshed.status_code == 200 and refreshed.json()["status"] == "RETURNED", refreshed.text

        resubmitted = client.post(f"/api/v1/monthly-returns/{return_id}/submit", headers=headers, json={})
        assert resubmitted.status_code == 200 and resubmitted.json()["status"] == "SUBMITTED", resubmitted.text

        reviewed = client.post(f"/api/v1/monthly-returns/{return_id}/cluster-review", headers=headers, json={})
        assert reviewed.status_code == 200 and reviewed.json()["status"] == "CLUSTER_REVIEWED", reviewed.text

        approved = client.post(f"/api/v1/monthly-returns/{return_id}/block-approve", headers=headers, json={})
        assert approved.status_code == 200 and approved.json()["status"] == "BLOCK_APPROVED", approved.text

        locked = client.post("/api/v1/monthly-returns/generate", headers=headers, json={"school_id":school_id,"year":2026,"month":9})
        assert locked.status_code == 400, locked.text

        rows = client.get("/api/v1/monthly-returns?year=2026&month=9", headers=headers)
        assert rows.status_code == 200 and len(rows.json()) == 1
        assert rows.json()[0]["status"] == "BLOCK_APPROVED"

        report = client.get(f"/api/v1/monthly-returns/{return_id}/report", headers=headers)
        assert report.status_code == 200, report.text
        report_body = report.json()
        assert report_body["report_type"] == "MONTHLY_RETURN"
        actions = report_body["actions"]
        assert [x["action"] for x in actions] == ["SUBMIT","RETURN","SUBMIT","CLUSTER_REVIEW","BLOCK_APPROVE"]

        with runtime.connect() as conn:
            audit_count = conn.execute("SELECT COUNT(*) FROM audit_log WHERE entity_type='MONTHLY_RETURN' AND entity_id=?", (return_id,)).fetchone()[0]
        assert audit_count >= 7

        print(json.dumps({
            "ok": True,
            "phase": "5C2-F",
            "hierarchy_scope": True,
            "monthly_generation": True,
            "verified_only_aggregation": True,
            "exception_tracking": True,
            "submit_return_resubmit": True,
            "cluster_review": True,
            "block_approval": True,
            "workflow_lock": True,
            "monthly_summary": True,
            "local_report_snapshot": True,
            "audit_log": True,
        }, indent=2))


if __name__ == "__main__":
    main()
