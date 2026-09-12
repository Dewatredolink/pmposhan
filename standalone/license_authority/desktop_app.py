from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn

APP_TITLE = "PM POSHAN License Authority"
HOST = "127.0.0.1"
_DEVNULL_HANDLES: list[object] = []


def _ensure_windowed_stdio() -> None:
    """Provide harmless streams when PyInstaller runs with console=False.

    In a Windows GUI executable sys.stdout/sys.stderr can be None. Uvicorn's
    default logging formatter probes stream.isatty(), which otherwise crashes
    before the local authority server starts.
    """
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            stream = open(os.devnull, "w", encoding="utf-8", buffering=1)
            setattr(sys, name, stream)
            _DEVNULL_HANDLES.append(stream)


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def _wait_for_server(port: int, timeout: float = 12.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("LICENSE_AUTHORITY_SERVER_START_TIMEOUT")


def _self_test() -> int:
    from dashboard import OUTPUT_DIR, PRIVATE_KEY_FILE

    result = {
        "ok": PRIVATE_KEY_FILE.exists(),
        "app": "PM POSHAN License Authority",
        "private_key_present": PRIVATE_KEY_FILE.exists(),
        "private_key_path": str(PRIVATE_KEY_FILE),
        "output_dir": str(OUTPUT_DIR),
        "private_key_embedded": False,
    }
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


def main() -> int:
    _ensure_windowed_stdio()

    if "--self-test" in sys.argv:
        return _self_test()

    # The private signing key remains external to the application bundle.
    # dashboard.py reads it from PMPOSHAN_LICENSE_PRIVATE_KEY_FILE or the
    # default C:\\PMPoshan-License-Authority\\PRIVATE_KEY_B64.txt path.
    from dashboard import app

    port = _free_loopback_port()
    # Disable Uvicorn's console-oriented default logging configuration. The
    # desktop bundle is a windowed PyInstaller executable with no console.
    config = uvicorn.Config(
        app,
        host=HOST,
        port=port,
        log_level="warning",
        access_log=False,
        log_config=None,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None

    server_thread = threading.Thread(target=server.run, name="pmposhan-license-authority", daemon=True)
    server_thread.start()

    try:
        _wait_for_server(port)
        import webview

        storage_path = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PMPoshanLicenseAuthority" / "WebView2"
        storage_path.mkdir(parents=True, exist_ok=True)

        webview.create_window(
            APP_TITLE,
            f"http://{HOST}:{port}",
            width=1180,
            height=820,
            min_size=(900, 650),
            resizable=True,
        )
        webview.start(debug=False, private_mode=False, storage_path=str(storage_path))
        return 0
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
