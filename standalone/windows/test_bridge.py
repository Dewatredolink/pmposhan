from __future__ import annotations

import base64
import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-bridge-test-"))
    os.environ["PMPOSHAN_DATA_DIR"] = str(temp_root)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    os.environ["LICENSE_PUBLIC_KEY_B64"] = base64.b64encode(public_key).decode("ascii")

    from fastapi.testclient import TestClient
    import runtime
    from bridge import app

    runtime.init_db()

    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200, health.text
        installation_id = health.json()["installation_id"]

        setup = client.get("/api/v1/setup/status")
        assert setup.status_code == 200, setup.text
        assert setup.json()["needs_admin"] is True

        created = client.post(
            "/api/v1/setup/admin",
            json={
                "username": "system.admin",
                "password": "StrongTestPassword123!",
                "display_name": "System Admin",
            },
        )
        assert created.status_code == 200, created.text

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "system.admin", "password": "StrongTestPassword123!"},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me = client.get("/api/v1/me", headers=headers)
        assert me.status_code == 200, me.text
        assert "SYSTEM_ADMIN" in me.json()["realm_roles"]

        today = date.today()
        payload = {
            "product": "PM_POSHAN",
            "license_id": "TEST-STANDALONE",
            "organization": "Runtime Test School",
            "installation_id": installation_id,
            "edition": "STANDALONE",
            "valid_from": str(today - timedelta(days=1)),
            "valid_until": str(today + timedelta(days=30)),
            "max_schools": 1,
        }
        signature = base64.b64encode(private_key.sign(canonical(payload))).decode("ascii")

        activate = client.post(
            "/api/v1/license/activate",
            json={"license": payload, "signature": signature},
        )
        assert activate.status_code == 200, activate.text
        assert activate.json()["active"] is True

        backup = client.post("/api/v1/backups", headers=headers)
        assert backup.status_code == 200, backup.text
        assert Path(backup.json()["path"]).exists()

        logout = client.post("/api/v1/auth/logout", headers=headers)
        assert logout.status_code == 200, logout.text

        blocked = client.get("/api/v1/me", headers=headers)
        assert blocked.status_code == 401

        print(json.dumps({
            "ok": True,
            "bridge": True,
            "loopback_api": "127.0.0.1:8765",
            "first_run_setup": True,
            "local_login": True,
            "signed_license_activation": True,
            "authenticated_backup": True,
            "logout_invalidates_session": True,
        }, indent=2))


if __name__ == "__main__":
    main()
