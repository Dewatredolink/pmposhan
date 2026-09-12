from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-phase5c2e-test-"))
    os.environ["PMPOSHAN_DATA_DIR"] = str(temp_root)

    from fastapi.testclient import TestClient
    import runtime
    from bridge import app

    runtime.init_db()

    district_id = str(uuid.uuid4())
    block_id = str(uuid.uuid4())
    cluster_id = str(uuid.uuid4())
    school_id = str(uuid.uuid4())
    menu_id = str(uuid.uuid4())

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
            (cluster_id, "CL-001", block_id, "Sample Cluster", "नमुना केंद्र"),
        )
        conn.execute(
            """
            INSERT INTO schools
                (id, code, udise_code, cluster_id, name_en, name_mr, village, class_1_5_strength, class_6_8_strength)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                school_id,
                "SCHOOL-001",
                "27360803502",
                cluster_id,
                "Gaymukhpada",
                "गायमुखपाडा",
                "Gaymukhpada",
                40,
                20,
            ),
        )
        conn.execute(
            """
            INSERT INTO menus (id, code, name_en, name_mr, week_pattern, day_of_week)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (menu_id, "MENU-01", "Khichdi", "खिचडी", "CUSTOM", 3),
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

        empty_plan = client.get(
            f"/api/v1/menu-plan?school_id={school_id}&menu_date=2026-09-02",
            headers=headers,
        )
        assert empty_plan.status_code == 200, empty_plan.text
        assert empty_plan.json()["plan"] is None

        saved_plan = client.put(
            "/api/v1/menu-plan",
            headers=headers,
            json={
                "school_id": school_id,
                "menu_date": "2026-09-02",
                "menu_id": menu_id,
                "remarks": "Wednesday menu",
            },
        )
        assert saved_plan.status_code == 200, saved_plan.text
        assert saved_plan.json()["plan"]["menu_id"] == menu_id
        assert saved_plan.json()["plan"]["menu_code"] == "MENU-01"

        saved_plan_update = client.put(
            "/api/v1/menu-plan",
            headers=headers,
            json={
                "school_id": school_id,
                "menu_date": "2026-09-02",
                "menu_id": menu_id,
                "remarks": "Updated plan",
            },
        )
        assert saved_plan_update.status_code == 200, saved_plan_update.text
        assert saved_plan_update.json()["plan"]["remarks"] == "Updated plan"

        before_defaults = client.get(
            f"/api/v1/calendar/month?school_id={school_id}&year=2026&month=9",
            headers=headers,
        )
        assert before_defaults.status_code == 200, before_defaults.text
        before_rows = before_defaults.json()
        assert len(before_rows) == 30
        assert all(row["configured"] is False for row in before_rows)
        sunday_before = next(row for row in before_rows if row["date"] == "2026-09-06")
        assert sunday_before["day_type"] == "SUNDAY"
        assert sunday_before["meal_required"] is False

        defaults = client.post(
            "/api/v1/calendar/month/defaults",
            headers=headers,
            json={"school_id": school_id, "year": 2026, "month": 9},
        )
        assert defaults.status_code == 200, defaults.text
        assert defaults.json()["created"] == 30

        defaults_again = client.post(
            "/api/v1/calendar/month/defaults",
            headers=headers,
            json={"school_id": school_id, "year": 2026, "month": 9},
        )
        assert defaults_again.status_code == 200, defaults_again.text
        assert defaults_again.json()["created"] == 0

        holiday = client.put(
            "/api/v1/calendar/day",
            headers=headers,
            json={
                "school_id": school_id,
                "date": "2026-09-15",
                "day_type": "PUBLIC_HOLIDAY",
                "meal_required": False,
                "title_en": "Public Holiday",
                "title_mr": "सार्वजनिक सुट्टी",
            },
        )
        assert holiday.status_code == 200, holiday.text

        calendar = client.get(
            f"/api/v1/calendar/month?school_id={school_id}&year=2026&month=9",
            headers=headers,
        )
        assert calendar.status_code == 200, calendar.text
        rows = calendar.json()
        assert len(rows) == 30
        assert all(row["configured"] is True for row in rows)
        holiday_row = next(row for row in rows if row["date"] == "2026-09-15")
        assert holiday_row["day_type"] == "PUBLIC_HOLIDAY"
        assert holiday_row["meal_required"] is False

        with runtime.connect() as conn:
            admin_id = conn.execute(
                "SELECT id FROM local_users WHERE username='system.admin'"
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO daily_meal_entries
                    (id, school_id, meal_date, menu_id, meals_class_1_5, meals_class_6_8, total_meals,
                     tasting_done, hygiene_ok, status, entered_by_user_id, entered_by_username,
                     verified_by_user_id, verified_by_username, verified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, 'VERIFIED', ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    school_id,
                    "2026-09-01",
                    menu_id,
                    30,
                    10,
                    40,
                    admin_id,
                    "system.admin",
                    admin_id,
                    "system.admin",
                    runtime.utc_now(),
                ),
            )

        compliance = client.get(
            f"/api/v1/compliance/month?school_id={school_id}&year=2026&month=9",
            headers=headers,
        )
        assert compliance.status_code == 200, compliance.text
        comp = compliance.json()
        assert comp["required_days"] == 25, comp
        assert comp["complete_days"] == 1, comp
        assert comp["missing_days"] == 24, comp
        assert comp["compliance_percent"] == 4.0, comp
        assert "2026-09-01" not in comp["missing_dates"]
        assert "2026-09-15" not in comp["missing_dates"]
        assert "2026-09-02" in comp["missing_dates"]

        with runtime.connect() as conn:
            audit_count = conn.execute(
                """
                SELECT COUNT(*) FROM audit_log
                WHERE entity_type IN ('MENU_SCHEDULE','SCHOOL_CALENDAR','SCHOOL_CALENDAR_DAY')
                """
            ).fetchone()[0]
        assert audit_count >= 4

        print(
            "{\n"
            '  "ok": true,\n'
            '  "phase": "5C2-E",\n'
            '  "menu_planner": true,\n'
            '  "date_wise_menu_schedule": true,\n'
            '  "calendar_month_defaults": true,\n'
            '  "holiday_override": true,\n'
            '  "monthly_compliance": true,\n'
            '  "missing_meal_detection": true,\n'
            '  "verified_meal_completion": true,\n'
            '  "audit_log": true\n'
            "}"
        )


if __name__ == "__main__":
    main()
