from __future__ import annotations

import os
import secrets
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import runtime

app = FastAPI(title="PM POSHAN Standalone Bridge", version="1.0")

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "PMPOSHAN_ALLOWED_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

_sessions: dict[str, dict[str, Any]] = {}


class LoginRequest(BaseModel):
    username: str
    password: str


class SetupAdminRequest(BaseModel):
    username: str
    password: str
    display_name: str = "System Admin"


class LicensePackage(BaseModel):
    license: dict[str, Any]
    signature: str


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
    return token


def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = _bearer_token(authorization)
    user = _sessions.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="SESSION_INVALID")
    return user


def require_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user.get("role") != "SYSTEM_ADMIN":
        raise HTTPException(status_code=403, detail="SYSTEM_ADMIN_REQUIRED")
    return user


@app.on_event("startup")
def startup() -> None:
    runtime.init_db()


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "mode": "standalone",
        "installation_id": runtime.get_installation_id(),
        "app_version": runtime.APP_VERSION,
    }


@app.get("/api/v1/setup/status")
def setup_status() -> dict[str, Any]:
    return runtime.first_run_status()


@app.post("/api/v1/setup/admin")
def setup_admin(body: SetupAdminRequest) -> dict[str, Any]:
    try:
        user_id = runtime.create_first_admin(body.username, body.password, body.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"created": True, "user_id": user_id}


@app.post("/api/v1/auth/login")
def login(body: LoginRequest) -> dict[str, Any]:
    user = runtime.authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="INVALID_CREDENTIALS")
    token = secrets.token_urlsafe(48)
    _sessions[token] = user
    return {"access_token": token, "token_type": "bearer", "user": user}


@app.post("/api/v1/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    token = _bearer_token(authorization)
    _sessions.pop(token, None)
    return {"ok": True}


@app.get("/api/v1/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {
        "sub": user["id"],
        "preferred_username": user["username"],
        "name": user.get("display_name") or user["username"],
        "realm_roles": [user["role"]],
        "role": user["role"],
        "mode": "standalone",
    }


@app.get("/api/v1/license/status")
def license_status() -> dict[str, Any]:
    return runtime.license_status()


@app.post("/api/v1/license/activate")
def license_activate(body: LicensePackage) -> dict[str, Any]:
    try:
        runtime.store_license(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    status = runtime.license_status()
    if not status.get("active"):
        raise HTTPException(status_code=400, detail=status.get("reason", "LICENSE_INVALID"))
    return status


@app.get("/api/v1/installation")
def installation(user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return {
        "installation_id": runtime.get_installation_id(),
        "app_version": runtime.APP_VERSION,
        "schema_version": runtime.SCHEMA_VERSION,
        "data_dir": str(runtime.APP_DIR),
    }


@app.post("/api/v1/backups")
def create_backup(user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    path = runtime.create_backup()
    return {"ok": True, "file_name": path.name, "path": str(path)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("bridge:app", host="127.0.0.1", port=8765, reload=False)
