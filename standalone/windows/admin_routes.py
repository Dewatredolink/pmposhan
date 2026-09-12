from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import admin_service
import runtime


class UserCreateRequest(BaseModel):
    username: str
    display_name: str = ""
    password: str
    role: str
    school_ids: list[str] = []
    preferred_language: str = "mr"


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    active: bool | None = None
    school_ids: list[str] | None = None
    preferred_language: str | None = None


class PasswordResetRequest(BaseModel):
    password: str


def build_router(require_admin: Callable[..., dict[str, Any]], service_error: Callable[[Exception], Exception]) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/admin/users")
    def list_users(user: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
        return admin_service.list_users()

    @router.post("/admin/users")
    def create_user(body: UserCreateRequest, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        try:
            return admin_service.create_user(body.model_dump(), user["id"])
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.put("/admin/users/{user_id}")
    def update_user(user_id: str, body: UserUpdateRequest, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        try:
            return admin_service.update_user(user_id, body.model_dump(exclude_unset=True), user["id"])
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.post("/admin/users/{user_id}/reset-password")
    def reset_user_password(user_id: str, body: PasswordResetRequest, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        try:
            return admin_service.reset_password(user_id, body.password, user["id"])
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.post("/admin/restore-standard-masters")
    def restore_standard_masters(user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        try:
            return admin_service.restore_standard_masters(user["id"])
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.get("/admin/device")
    def device_summary(user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return {
            "installation_id": runtime.get_installation_id(),
            "app_version": runtime.APP_VERSION,
            "schema_version": runtime.SCHEMA_VERSION,
            "data_dir": str(runtime.APP_DIR),
            "license": runtime.license_status(),
        }

    return router
