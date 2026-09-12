from __future__ import annotations

import base64
import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption, PublicFormat


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pmposhan-license-authority-test-"))
    key_file = temp_root / "PRIVATE_KEY_B64.txt"
    out_dir = temp_root / "issued"

    private_key = Ed25519PrivateKey.generate()
    raw_private = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    key_file.write_text(base64.b64encode(raw_private).decode("ascii"), encoding="utf-8")

    os.environ["PMPOSHAN_LICENSE_PRIVATE_KEY_FILE"] = str(key_file)
    os.environ["PMPOSHAN_LICENSE_OUTPUT_DIR"] = str(out_dir)

    from fastapi.testclient import TestClient
    import dashboard

    with TestClient(dashboard.app) as client:
        status = client.get("/api/status")
        assert status.status_code == 200, status.text
        assert status.json()["private_key_present"] is True

        start = date.today()
        end = start + timedelta(days=364)
        installation_id = "9b63c5b7-0fd5-4b5b-99a4-3a05d725e41e"
        issued = client.post(
            "/api/issue",
            json={
                "installation_id": installation_id,
                "organization": "Test Z.P. School",
                "udise": "27360803502",
                "valid_from": start.isoformat(),
                "valid_until": end.isoformat(),
                "edition": "STANDALONE",
                "max_schools": 1,
                "license_id": "PM-STANDALONE-TEST-0001",
            },
        )
        assert issued.status_code == 200, issued.text
        body = issued.json()
        package = body["package"]
        saved = Path(body["saved_to"])
        assert saved.exists(), saved
        assert package["license"]["installation_id"] == installation_id

        canonical = dashboard.canonical(package["license"])
        signature = base64.b64decode(package["signature"], validate=True)
        public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        private_key.public_key().verify(signature, canonical)

        on_disk = json.loads(saved.read_text(encoding="utf-8"))
        assert on_disk == package

        print(json.dumps({
            "ok": True,
            "phase": "license-authority-desktop",
            "dashboard_api": True,
            "external_private_key": True,
            "signed_activation_package": True,
            "signature_verified": True,
            "issued_file_created": True,
        }, indent=2))


if __name__ == "__main__":
    main()
