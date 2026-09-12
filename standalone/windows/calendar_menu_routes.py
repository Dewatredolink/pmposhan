from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

import calendar_menu_service


def build_router(
    current_user: Callable[..., dict[str, Any]],
    service_error: Callable[[Exception], HTTPException],
) -> APIRouter:
    router = APIRouter()

    @router.get("/menu-plan")
    def get_menu_plan(
        school_id: str,
        menu_date: str,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return calendar_menu_service.get_menu_plan(school_id, menu_date)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.put("/menu-plan")
    def save_menu_plan(
        body: dict[str, Any],
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return calendar_menu_service.save_menu_plan(body, user)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.get("/calendar/month")
    def calendar_month(
        school_id: str,
        year: int,
        month: int,
        user: dict[str, Any] = Depends(current_user),
    ) -> list[dict[str, Any]]:
        try:
            return calendar_menu_service.calendar_month(school_id, year, month)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.post("/calendar/month/defaults")
    def calendar_defaults(
        body: dict[str, Any],
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return calendar_menu_service.create_month_defaults(body, user)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.put("/calendar/day")
    def calendar_day(
        body: dict[str, Any],
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return calendar_menu_service.save_calendar_day(body, user)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.get("/compliance/month")
    def compliance_month(
        school_id: str,
        year: int,
        month: int,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return calendar_menu_service.compliance_month(school_id, year, month)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    return router
