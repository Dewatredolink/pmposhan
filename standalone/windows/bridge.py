from __future__ import annotations

import os
import secrets
from datetime import date
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import admin_routes
import admin_service
import daily_routes
import master_service
import operations
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


class SchoolCreateRequest(BaseModel):
    code: str
    udise_code: str
    cluster_id: str
    name_en: str
    name_mr: str
    village: str | None = None
    class_1_5_strength: int = 0
    class_6_8_strength: int = 0
    active: bool = True


class SchoolUpdateRequest(BaseModel):
    code: str | None = None
    udise_code: str | None = None
    cluster_id: str | None = None
    name_en: str | None = None
    name_mr: str | None = None
    village: str | None = None
    class_1_5_strength: int | None = None
    class_6_8_strength: int | None = None
    active: bool | None = None


class AcademicYearCreateRequest(BaseModel):
    code: str
    start_date: str
    end_date: str
    is_current: bool = False


class AcademicYearUpdateRequest(BaseModel):
    code: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool | None = None


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


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc.args[0] if exc.args else exc))
    return HTTPException(status_code=400, detail=str(exc))


@app.on_event("startup")
def startup() -> None:
    runtime.init_db()
    admin_service.ensure_admin_schema()


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
    school_access = admin_service.user_school_access(user)
    return {
        "sub": user["id"],
        "username": user["username"],
        "preferred_username": user["username"],
        "name": user.get("display_name") or user["username"],
        "email": None,
        "roles": [user["role"]],
        "realm_roles": [user["role"]],
        "role": user["role"],
        "school_access": school_access,
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


@app.get("/api/v1/schools")
def list_schools(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    return admin_service.allowed_schools(user)


@app.post("/api/v1/schools")
def create_school(body: SchoolCreateRequest, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return operations.create_school(body.model_dump(), user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.get("/api/v1/schools/{school_id}")
def get_school(school_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    school = operations.get_school(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="SCHOOL_NOT_FOUND")
    return school


@app.put("/api/v1/schools/{school_id}")
def update_school(school_id: str, body: SchoolUpdateRequest, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return operations.update_school(school_id, body.model_dump(exclude_unset=True), user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.get("/api/v1/academic-years")
def list_academic_years(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    return operations.list_academic_years()


@app.post("/api/v1/academic-years")
def create_academic_year(body: AcademicYearCreateRequest, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return operations.create_academic_year(body.model_dump(), user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.put("/api/v1/academic-years/{year_id}")
def update_academic_year(year_id: str, body: AcademicYearUpdateRequest, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return operations.update_academic_year(year_id, body.model_dump(exclude_unset=True), user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.post("/api/v1/academic-years/{year_id}/make-current")
def make_academic_year_current(year_id: str, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return operations.make_academic_year_current(year_id, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.get("/api/v1/master/districts")
def master_districts(user: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    return master_service.list_districts()


@app.post("/api/v1/master/districts")
def master_create_district(body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.create_district(body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.put("/api/v1/master/districts/{row_id}")
def master_update_district(row_id: str, body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.update_district(row_id, body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.get("/api/v1/master/blocks")
def master_blocks(user: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    return master_service.list_blocks()


@app.post("/api/v1/master/blocks")
def master_create_block(body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.create_block(body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.put("/api/v1/master/blocks/{row_id}")
def master_update_block(row_id: str, body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.update_block(row_id, body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.get("/api/v1/master/clusters")
def master_clusters(user: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    return master_service.list_clusters()


@app.post("/api/v1/master/clusters")
def master_create_cluster(body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.create_cluster(body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.put("/api/v1/master/clusters/{row_id}")
def master_update_cluster(row_id: str, body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.update_cluster(row_id, body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.get("/api/v1/master/schools")
def master_schools(user: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    return master_service.list_schools()


@app.post("/api/v1/master/schools")
def master_create_school(body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.create_school(body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.put("/api/v1/master/schools/{row_id}")
def master_update_school(row_id: str, body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.update_school(row_id, body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.get("/api/v1/master/ingredients")
def master_ingredients(user: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    return master_service.list_ingredients()


@app.post("/api/v1/master/ingredients")
def master_create_ingredient(body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.create_ingredient(body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.put("/api/v1/master/ingredients/{row_id}")
def master_update_ingredient(row_id: str, body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.update_ingredient(row_id, body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.get("/api/v1/master/menus")
def master_menus(user: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    return master_service.list_menus()


@app.post("/api/v1/master/menus")
def master_create_menu(body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.create_menu(body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.put("/api/v1/master/menus/{row_id}")
def master_update_menu(row_id: str, body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.update_menu(row_id, body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.get("/api/v1/master/menus/{menu_id}/recipe-standard")
def master_recipe_standard(menu_id: str, on_date: str | None = None, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.get_recipe_standard(menu_id, on_date or date.today().isoformat())
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


@app.put("/api/v1/master/menus/{menu_id}/recipe-standard")
def master_save_recipe_standard(menu_id: str, body: dict[str, Any], user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return master_service.save_recipe_standard(menu_id, body, user["id"])
    except (ValueError, KeyError) as exc:
        raise _service_error(exc) from exc


app.include_router(admin_routes.build_router(require_admin, _service_error))
app.include_router(daily_routes.build_router(current_user, require_admin, _service_error))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("bridge:app", host="127.0.0.1", port=8765, reload=False)
