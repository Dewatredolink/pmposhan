import base64
import json
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import text
from app.db.session import engine

PRODUCT = "PM_POSHAN"
STATE_ID = 1

DDL = """
CREATE TABLE IF NOT EXISTS system_license_state (
    id INTEGER PRIMARY KEY,
    installation_id VARCHAR(64) NOT NULL UNIQUE,
    license_json TEXT NULL,
    signature_b64 TEXT NULL,
    activated_at TIMESTAMPTZ NULL
)
"""

def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def _public_key() -> Ed25519PublicKey:
    value = (os.getenv("LICENSE_PUBLIC_KEY_B64") or "").strip()
    if not value:
        raise RuntimeError("LICENSE_PUBLIC_KEY_NOT_CONFIGURED")
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) != 32:
            raise ValueError("Ed25519 public key must be 32 bytes")
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception as exc:
        raise RuntimeError("LICENSE_PUBLIC_KEY_INVALID") from exc

def ensure_state() -> str:
    with engine.begin() as conn:
        conn.execute(text(DDL))
        row = conn.execute(text("SELECT installation_id FROM system_license_state WHERE id=:id"), {"id": STATE_ID}).first()
        if row:
            return row[0]
        installation_id = str(uuid.uuid4())
        conn.execute(
            text("INSERT INTO system_license_state (id, installation_id) VALUES (:id, :installation_id)"),
            {"id": STATE_ID, "installation_id": installation_id},
        )
        return installation_id

def _row():
    installation_id = ensure_state()
    with engine.begin() as conn:
        return conn.execute(
            text("SELECT installation_id, license_json, signature_b64, activated_at FROM system_license_state WHERE id=:id"),
            {"id": STATE_ID},
        ).mappings().first()

def _school_count() -> int:
    with engine.begin() as conn:
        try:
            return int(conn.execute(text("SELECT COUNT(*) FROM schools")).scalar_one())
        except Exception:
            return 0

def _school_udise_codes() -> list[str]:
    with engine.begin() as conn:
        try:
            rows = conn.execute(
                text("SELECT udise_code FROM schools WHERE udise_code IS NOT NULL")
            ).scalars().all()
            return [str(value).strip() for value in rows if str(value).strip()]
        except Exception:
            return []


def _validate_dates(payload: dict[str, Any]) -> tuple[bool, str]:
    today = date.today()
    try:
        valid_from = date.fromisoformat(str(payload["valid_from"]))
        valid_until = date.fromisoformat(str(payload["valid_until"]))
    except Exception:
        return False, "LICENSE_DATE_INVALID"
    if today < valid_from:
        return False, "LICENSE_NOT_YET_VALID"
    if today > valid_until:
        return False, "LICENSE_EXPIRED"
    return True, "OK"

def validate_package(payload: dict[str, Any], signature_b64: str, installation_id: str | None = None) -> tuple[bool, str]:
    required = {
        "product", "license_id", "organization", "installation_id",
        "edition", "valid_from", "valid_until", "max_schools"
    }
    if not required.issubset(payload):
        return False, "LICENSE_FIELDS_MISSING"
    if payload.get("product") != PRODUCT:
        return False, "LICENSE_PRODUCT_MISMATCH"

    expected_installation = installation_id or ensure_state()
    if str(payload.get("installation_id")) != expected_installation:
        return False, "LICENSE_INSTALLATION_MISMATCH"

    ok, reason = _validate_dates(payload)
    if not ok:
        return ok, reason

    try:
        max_schools = int(payload.get("max_schools"))
        if max_schools < 1:
            return False, "LICENSE_MAX_SCHOOLS_INVALID"
        if _school_count() > max_schools:
            return False, "LICENSE_SCHOOL_LIMIT_EXCEEDED"
    except Exception:
        return False, "LICENSE_MAX_SCHOOLS_INVALID"

    edition = str(payload.get("edition") or "").strip().upper()
    if edition == "SCHOOL":
        licensed_udise = str(payload.get("udise") or "").strip()

        if not licensed_udise:
            return False, "LICENSE_UDISE_REQUIRED"

        school_udises = _school_udise_codes()

        if not school_udises:
            return False, "LICENSE_SCHOOL_NOT_CONFIGURED"

        if licensed_udise not in school_udises:
            return False, "LICENSE_UDISE_MISMATCH"

    try:
        signature = base64.b64decode(signature_b64, validate=True)
        _public_key().verify(signature, _canonical(payload))
    except RuntimeError as exc:
        return False, str(exc)
    except (InvalidSignature, ValueError, TypeError):
        return False, "LICENSE_SIGNATURE_INVALID"
    return True, "OK"

def activate(payload: dict[str, Any], signature_b64: str) -> dict[str, Any]:
    installation_id = ensure_state()
    ok, reason = validate_package(payload, signature_b64, installation_id)
    if not ok:
        return {"active": False, "reason": reason, "installation_id": installation_id}
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE system_license_state
                SET license_json=:license_json,
                    signature_b64=:signature_b64,
                    activated_at=:activated_at
                WHERE id=:id
            """),
            {
                "license_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                "signature_b64": signature_b64,
                "activated_at": datetime.now(timezone.utc),
                "id": STATE_ID,
            },
        )
    return status()

def status() -> dict[str, Any]:
    row = _row()
    installation_id = row["installation_id"]
    result = {
        "active": False,
        "installation_id": installation_id,
        "reason": "NOT_ACTIVATED",
        "license": None,
        "school_count": _school_count(),
    }
    if not (os.getenv("LICENSE_PUBLIC_KEY_B64") or "").strip():
        result["reason"] = "LICENSE_PUBLIC_KEY_NOT_CONFIGURED"
        return result
    if not row["license_json"] or not row["signature_b64"]:
        return result
    try:
        payload = json.loads(row["license_json"])
    except Exception:
        result["reason"] = "LICENSE_STORED_DATA_INVALID"
        return result
    ok, reason = validate_package(payload, row["signature_b64"], installation_id)
    result["active"] = ok
    result["reason"] = reason
    result["license"] = payload
    if row["activated_at"]:
        result["activated_at"] = row["activated_at"].isoformat()
    return result
