from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

import calendar_menu_routes
import daily_service
import inventory_routes
import monthly_routes
import school_profile_routes


def build_router(
    current_user: Callable[..., dict[str, Any]],
    require_admin: Callable[..., dict[str, Any]],
    service_error: Callable[[Exception], HTTPException],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/menus")
    def menus(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        return daily_service.list_menus()

    @router.get("/menus/{menu_id}/recipe-preview")
    def recipe_preview(
        menu_id: str,
        on_date: str,
        class_1_5: int = 0,
        class_6_8: int = 0,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return daily_service.get_recipe_preview(menu_id, on_date, class_1_5, class_6_8)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.get("/daily-operations")
    def daily_operations(
        school_id: str,
        meal_date: str,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return daily_service.get_daily_operations(school_id, meal_date)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.put("/daily-attendance")
    def daily_attendance(
        body: dict[str, Any],
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return daily_service.save_attendance(body, user)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.put("/daily-meal")
    def daily_meal(
        body: dict[str, Any],
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return daily_service.save_meal(body, user)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.post("/daily-operations/verify")
    def verify_daily_operations(
        body: dict[str, Any],
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return daily_service.verify_daily_operations(
                str(body.get("school_id") or ""),
                str(body.get("meal_date") or ""),
                user,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    router.include_router(inventory_routes.build_router(current_user, service_error))
    router.include_router(calendar_menu_routes.build_router(current_user, service_error))
    router.include_router(monthly_routes.build_router(current_user, service_error))
    router.include_router(school_profile_routes.build_router(current_user, service_error))
    return router
