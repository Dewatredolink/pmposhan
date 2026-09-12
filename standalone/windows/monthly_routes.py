from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

import monthly_service


def build_router(
    current_user: Callable[..., dict[str, Any]],
    service_error: Callable[[Exception], HTTPException],
) -> APIRouter:
    router = APIRouter()

    @router.get("/hierarchy/scope")
    def hierarchy_scope(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        return monthly_service.hierarchy_scope()

    @router.get("/monthly-returns")
    def monthly_returns(year: int, month: int, user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        try:
            return monthly_service.list_monthly_returns(year, month)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.get("/monthly-returns/summary")
    def monthly_returns_summary(year: int, month: int, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return monthly_service.summary(year, month)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.post("/monthly-returns/generate")
    def generate_monthly_return(body: dict[str, Any], user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return monthly_service.generate(body, user)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.post("/monthly-returns/{return_id}/submit")
    def submit_monthly_return(return_id: str, body: dict[str, Any] | None = None, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return monthly_service.submit(return_id, user, (body or {}).get("remarks"))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.post("/monthly-returns/{return_id}/cluster-review")
    def cluster_review(return_id: str, body: dict[str, Any] | None = None, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return monthly_service.cluster_review(return_id, user, (body or {}).get("remarks"))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.post("/monthly-returns/{return_id}/block-approve")
    def block_approve(return_id: str, body: dict[str, Any] | None = None, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return monthly_service.block_approve(return_id, user, (body or {}).get("remarks"))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.post("/monthly-returns/{return_id}/return")
    def return_for_correction(return_id: str, body: dict[str, Any] | None = None, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return monthly_service.return_for_correction(return_id, user, (body or {}).get("remarks"))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    @router.get("/monthly-returns/{return_id}/report")
    def monthly_return_report(return_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return monthly_service.report(return_id)
        except (ValueError, KeyError) as exc:
            raise service_error(exc) from exc

    return router
