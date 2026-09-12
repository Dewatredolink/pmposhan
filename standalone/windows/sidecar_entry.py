from __future__ import annotations

import os
import sys
from pathlib import Path

# The public verification key is intentionally distributable. The private
# signing key must never be packaged with the application.
PUBLIC_LICENSE_KEY_B64 = "3vsN+dDnufUGNaUnev+i4WMYqRU5OocDl2jXIUWvoFA="


def _default_data_dir() -> Path:
    # The Windows desktop bundle is installed in current-user mode. Store all
    # mutable standalone data in the current user's LocalAppData so the app
    # does not require administrator rights or ProgramData ACL changes.
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "PMPoshan"

    # Fallback for unusual/non-Windows environments and development shells.
    return Path.home() / ".pmposhan"


def _prepare_environment() -> None:
    os.environ.setdefault("PMPOSHAN_DATA_DIR", str(_default_data_dir()))
    os.environ.setdefault("LICENSE_PUBLIC_KEY_B64", PUBLIC_LICENSE_KEY_B64)
    os.environ.setdefault(
        "PMPOSHAN_ALLOWED_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,http://tauri.localhost,tauri://localhost",
    )


def _bridge_port() -> int:
    raw = (os.environ.get("PMPOSHAN_BRIDGE_PORT") or "8765").strip()
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError("PMPOSHAN_BRIDGE_PORT_INVALID") from exc
    if port < 1024 or port > 65535:
        raise RuntimeError("PMPOSHAN_BRIDGE_PORT_INVALID")
    return port


def _configure_bundled_schema(runtime_module: object) -> None:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        schema_path = Path(bundle_root) / "standalone" / "schema.sql"
        setattr(runtime_module, "SCHEMA_PATH", schema_path)


def main() -> None:
    _prepare_environment()

    import runtime

    _configure_bundled_schema(runtime)

    from bridge import app
    import uvicorn

    # Standalone bridge is intentionally loopback-only. Never expose it on
    # 0.0.0.0 from the packaged desktop application.
    uvicorn.run(app, host="127.0.0.1", port=_bridge_port(), log_level="warning")


if __name__ == "__main__":
    main()
