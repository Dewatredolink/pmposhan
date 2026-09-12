from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_VERSION = "1.0-standalone-dev"
SCHEMA_VERSION = 1
APP_DIR = Path(os.environ.get("PMPOSHAN_DATA_DIR", Path.home() / "PMPoshanStandalone"))
DB_PATH = APP_DIR / "data" / "pmposhan.db"
BACKUP_DIR = APP_DIR / "backups"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema.sql"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    (APP_DIR / "data").mkdir(parents=True, exist_ok=True)
    (APP_DIR / "documents").mkdir(parents=True, exist_ok=True)
    (APP_DIR / "photos").mkdir(parents=True, exist_ok=True)
    (APP_DIR / "reports").mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    ensure_dirs()
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect() as conn:
        conn.executescript(schema)
        row = conn.execute("SELECT id FROM installation_state WHERE id=1").fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO installation_state
                    (id, installation_id, created_at, app_version, schema_version)
                VALUES (1, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), utc_now(), APP_VERSION, SCHEMA_VERSION),
            )


def get_installation_id() -> str:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT installation_id FROM installation_state WHERE id=1").fetchone()
        if not row:
            raise RuntimeError("Installation state not initialized")
        return str(row[0])


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return "pbkdf2_sha256$310000$%s$%s" % (
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, rounds, salt_b64, digest_b64 = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def create_local_user(username: str, password: str, role: str, display_name: str = "") -> str:
    init_db()
    if role not in {"SYSTEM_ADMIN", "HEADMASTER", "TEACHER"}:
        raise ValueError("Invalid local role")
    user_id = str(uuid.uuid4())
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO local_users
                (id, username, password_hash, display_name, role, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (user_id, username.strip().lower(), _password_hash(password), display_name.strip(), role, now, now),
        )
    return user_id


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, display_name, role, active FROM local_users WHERE username=?",
            (username.strip().lower(),),
        ).fetchone()
        if not row or not row["active"] or not verify_password(password, row["password_hash"]):
            return None
        now = utc_now()
        conn.execute("UPDATE local_users SET last_login_at=?, updated_at=? WHERE id=?", (now, now, row["id"]))
        return {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
        }


def license_status() -> dict[str, Any]:
    init_db()
    installation_id = get_installation_id()
    with connect() as conn:
        row = conn.execute(
            "SELECT license_json, signature_b64, activated_at FROM license_state WHERE id=1"
        ).fetchone()
        if not row or not row["license_json"]:
            return {"active": False, "reason": "LICENSE_REQUIRED", "installation_id": installation_id}
        try:
            payload = json.loads(row["license_json"])
        except Exception:
            return {"active": False, "reason": "LICENSE_CORRUPT", "installation_id": installation_id}
        if payload.get("installation_id") != installation_id:
            return {"active": False, "reason": "LICENSE_INSTALLATION_MISMATCH", "installation_id": installation_id}
        return {
            "active": True,
            "reason": "OK",
            "installation_id": installation_id,
            "license": payload,
            "activated_at": row["activated_at"],
        }


def store_license(package: dict[str, Any]) -> None:
    init_db()
    payload = package.get("license")
    signature = package.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        raise ValueError("Invalid license package")
    if payload.get("installation_id") != get_installation_id():
        raise ValueError("LICENSE_INSTALLATION_MISMATCH")
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO license_state (id, license_json, signature_b64, activated_at, last_validated_at)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                license_json=excluded.license_json,
                signature_b64=excluded.signature_b64,
                activated_at=excluded.activated_at,
                last_validated_at=excluded.last_validated_at
            """,
            (json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True), signature, now, now),
        )


def _consistent_db_copy(target: Path) -> None:
    with connect() as source, sqlite3.connect(target) as dest:
        source.backup(dest)


def create_backup() -> Path:
    init_db()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"PMPoshan_Backup_{stamp}.zip"
    snapshot = APP_DIR / "data" / "pmposhan.backup.tmp.db"
    if snapshot.exists():
        snapshot.unlink()
    _consistent_db_copy(snapshot)
    try:
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(snapshot, arcname="data/pmposhan.db")
            for folder in ("documents", "photos", "reports"):
                root = APP_DIR / folder
                if root.exists():
                    for file in root.rglob("*"):
                        if file.is_file():
                            zf.write(file, arcname=str(file.relative_to(APP_DIR)))
            zf.writestr(
                "backup.json",
                json.dumps({"created_at": utc_now(), "installation_id": get_installation_id()}, indent=2),
            )
    finally:
        snapshot.unlink(missing_ok=True)

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO backup_history
                (id, created_at, file_name, file_path, sha256, size_bytes, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, 'VERIFIED', ?)
            """,
            (
                str(uuid.uuid4()),
                utc_now(),
                target.name,
                str(target),
                digest,
                target.stat().st_size,
                "Automatic standalone backup",
            ),
        )
    return target


def restore_backup(backup_file: str | Path) -> None:
    backup_file = Path(backup_file)
    if not backup_file.exists():
        raise FileNotFoundError(backup_file)
    ensure_dirs()
    with zipfile.ZipFile(backup_file, "r") as zf:
        names = set(zf.namelist())
        if "data/pmposhan.db" not in names:
            raise ValueError("Backup does not contain data/pmposhan.db")
        temp_db = APP_DIR / "data" / "pmposhan.restore.tmp.db"
        temp_db.unlink(missing_ok=True)
        with zf.open("data/pmposhan.db") as src, temp_db.open("wb") as dst:
            shutil.copyfileobj(src, dst)

    with sqlite3.connect(temp_db) as test_conn:
        result = test_conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            temp_db.unlink(missing_ok=True)
            raise ValueError(f"Backup database integrity check failed: {result}")

    safety = APP_DIR / "data" / "pmposhan.before_restore.db"
    safety.unlink(missing_ok=True)
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, safety)
    temp_db.replace(DB_PATH)


if __name__ == "__main__":
    init_db()
    print(json.dumps({"ok": True, "db": str(DB_PATH), "installation_id": get_installation_id()}, indent=2))
