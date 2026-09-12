from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import school_profile_service


class SchoolProfileUpsertRequest(BaseModel):
    kitchen_type: str = "SCHOOL_KITCHEN"
    cooking_agency: str | None = None
    headmaster_name: str | None = None
    meal_incharge_name: str | None = None
    contact_mobile: str | None = None


def build_router(
    current_user: Callable[..., dict[str, Any]],
    service_error: Callable[[Exception], Exception],
) -> APIRouter:
    # This router is nested inside daily_routes, whose parent already owns the
    # /api/v1 prefix. Keeping this child prefix-free avoids /api/v1/api/v1/...
    router = APIRouter()

    @router.get("/school-profiles/{school_id}")
    def get_school_profile(
        school_id: str,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return school_profile_service.get_school_profile(school_id, user)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.put("/school-profiles/{school_id}")
    def save_school_profile(
        school_id: str,
        body: SchoolProfileUpsertRequest,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return school_profile_service.upsert_school_profile(school_id, body.model_dump(), user)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    return router
