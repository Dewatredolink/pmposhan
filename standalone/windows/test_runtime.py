from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-standalone-test-"))
    os.environ["PMPOSHAN_DATA_DIR"] = str(temp_root)

    import runtime

    runtime.init_db()
    installation_id = runtime.get_installation_id()
    assert installation_id

    user_id = runtime.create_local_user(
        username="system.admin",
        password="StrongTestPassword123!",
        role="SYSTEM_ADMIN",
        display_name="System Admin",
    )
    assert user_id
    assert runtime.authenticate("system.admin", "wrong-password") is None
    user = runtime.authenticate("system.admin", "StrongTestPassword123!")
    assert user and user["role"] == "SYSTEM_ADMIN"

    status = runtime.license_status()
    assert status["active"] is False
    assert status["reason"] == "LICENSE_REQUIRED"

    package = {
        "license": {
            "product": "PM_POSHAN",
            "edition": "STANDALONE",
            "license_id": "TEST-LICENSE",
            "organization": "Runtime Test School",
            "installation_id": installation_id,
            "udise": "TEST-UDISE",
        },
        "signature": "TEST-SIGNATURE-NOT-YET-VERIFIED",
    }
    runtime.store_license(package)
    status = runtime.license_status()
    assert status["active"] is True

    backup = runtime.create_backup()
    assert backup.exists()

    with runtime.connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM local_users").fetchone()[0]
    assert before == 1

    print(json.dumps({
        "ok": True,
        "installation_id": installation_id,
        "local_auth": True,
        "sqlite": True,
        "backup": str(backup),
        "license_storage": True,
        "note": "Ed25519 signature verification is intentionally the next Phase 5B step.",
    }, indent=2))

    shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
