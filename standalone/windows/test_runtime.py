from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-standalone-test-"))
    os.environ["PMPOSHAN_DATA_DIR"] = str(temp_root)

    private_key = Ed25519PrivateKey.generate()
    public_raw = private_key.public_key().public_bytes_raw()
    os.environ["LICENSE_PUBLIC_KEY_B64"] = base64.b64encode(public_raw).decode("ascii")

    import runtime

    runtime.init_db()
    installation_id = runtime.get_installation_id()
    assert installation_id

    first = runtime.first_run_status()
    assert first["admin_created"] is False
    assert first["license_active"] is False
    assert first["ready"] is False

    user_id = runtime.create_first_admin(
        username="system.admin",
        password="StrongTestPassword123!",
        display_name="System Admin",
    )
    assert user_id
    try:
        runtime.create_first_admin("another.admin", "AnotherStrongPassword123!")
        raise AssertionError("second first-run admin should not be allowed")
    except ValueError as exc:
        assert str(exc) == "FIRST_ADMIN_ALREADY_CREATED"

    assert runtime.authenticate("system.admin", "wrong-password") is None
    user = runtime.authenticate("system.admin", "StrongTestPassword123!")
    assert user and user["role"] == "SYSTEM_ADMIN"

    today = date.today()
    payload = {
        "product": "PM_POSHAN",
        "edition": "STANDALONE",
        "license_id": "TEST-LICENSE",
        "organization": "Runtime Test School",
        "installation_id": installation_id,
        "udise": "TEST-UDISE",
        "valid_from": today.isoformat(),
        "valid_until": (today + timedelta(days=365)).isoformat(),
        "max_schools": 1,
    }
    signature = base64.b64encode(private_key.sign(canonical(payload))).decode("ascii")
    package = {"license": payload, "signature": signature}

    status = runtime.store_license(package)
    assert status["active"] is True
    assert status["reason"] == "OK"

    tampered = dict(payload)
    tampered["organization"] = "Tampered School"
    ok, reason = runtime.validate_license_package(tampered, signature)
    assert ok is False
    assert reason == "LICENSE_SIGNATURE_INVALID"

    final_first = runtime.first_run_status()
    assert final_first["admin_created"] is True
    assert final_first["license_active"] is True
    assert final_first["ready"] is True

    backup = runtime.create_backup()
    assert backup.exists()

    with runtime.connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM local_users").fetchone()[0]
    assert before == 1

    print(json.dumps({
        "ok": True,
        "installation_id": installation_id,
        "local_auth": True,
        "first_run_admin": True,
        "sqlite": True,
        "backup": str(backup),
        "license_signature": "Ed25519 verified",
        "tamper_blocked": True,
        "ready": final_first["ready"],
    }, indent=2))

    shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
