from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

import inventory_service


def build_router(
    current_user: Callable[..., dict[str, Any]],
    service_error: Callable[[Exception], HTTPException],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def require_headmaster(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user.get("role") not in {"HEADMASTER", "SYSTEM_ADMIN"}:
            raise HTTPException(status_code=403, detail="HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED")
        return user

    @router.get("/ingredients")
    def ingredients(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        return inventory_service.list_ingredients()

    @router.post("/stock/opening-balance")
    def opening_balance(body: dict[str, Any], user: dict[str, Any] = Depends(require_headmaster)) -> dict[str, Any]:
        try:
            return inventory_service.create_opening_balance(body, user)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.get("/stock/balances")
    def balances(school_id: str, user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        try:
            return inventory_service.list_balances(school_id)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.get("/stock/ledger")
    def ledger(
        school_id: str,
        ingredient_id: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        user: dict[str, Any] = Depends(current_user),
    ) -> list[dict[str, Any]]:
        try:
            return inventory_service.list_ledger(school_id, ingredient_id, from_date, to_date)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.get("/stock/receipts")
    def receipts(school_id: str, user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        try:
            return inventory_service.list_receipts(school_id)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.post("/stock/receipts")
    def create_receipt(body: dict[str, Any], user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return inventory_service.create_receipt(body, user)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.get("/stock/adjustments")
    def adjustments(school_id: str, user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        try:
            return inventory_service.list_adjustments(school_id)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.post("/stock/adjustments")
    def create_adjustment(body: dict[str, Any], user: dict[str, Any] = Depends(require_headmaster)) -> dict[str, Any]:
        try:
            return inventory_service.create_adjustment(body, user)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.get("/stock/physical-verifications")
    def physical_verifications(school_id: str, user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        try:
            return inventory_service.list_physical_verifications(school_id)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.post("/stock/physical-verifications")
    def create_physical_verification(body: dict[str, Any], user: dict[str, Any] = Depends(require_headmaster)) -> dict[str, Any]:
        try:
            return inventory_service.create_physical_verification(body, user)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    return router
