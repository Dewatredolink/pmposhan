from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[2]
EXE = Path(__file__).resolve().parent / "dist" / "pmposhan-bridge.exe"


def wait_for_health(process: subprocess.Popen[bytes], timeout: float = 25.0) -> dict:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Sidecar exited early with code {process.returncode}")
        try:
            response = httpx.get("http://127.0.0.1:8765/api/v1/health", timeout=1.0)
            if response.status_code == 200:
                return response.json()
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Sidecar health endpoint did not become ready: {last_error}")


def main() -> None:
    if not EXE.exists():
        raise FileNotFoundError(f"Build the sidecar first: {EXE}")

    with tempfile.TemporaryDirectory(prefix="pmposhan-sidecar-smoke-") as temp_dir:
        env = os.environ.copy()
        env["PMPOSHAN_DATA_DIR"] = temp_dir

        process = subprocess.Popen(
            [str(EXE)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            health = wait_for_health(process)
            db_path = Path(temp_dir) / "data" / "pmposhan.db"
            if not health.get("ok") or health.get("mode") != "standalone":
                raise AssertionError(f"Unexpected health response: {health}")
            if not health.get("installation_id"):
                raise AssertionError("Packaged runtime did not create an installation ID")
            if not db_path.exists():
                raise AssertionError(f"SQLite database was not created: {db_path}")

            print(json.dumps({
                "ok": True,
                "phase": "5D-A",
                "pyinstaller_exe": True,
                "loopback_health": True,
                "bundled_schema": True,
                "sqlite_created": True,
                "installation_id": health["installation_id"],
                "exe": str(EXE),
            }, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
