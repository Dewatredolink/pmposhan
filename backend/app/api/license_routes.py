from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.licensing.service import activate, status

router = APIRouter(prefix="/license", tags=["license"])

class ActivationRequest(BaseModel):
    license: dict[str, Any]
    signature: str

@router.get("/status")
def license_status():
    return status()

@router.post("/activate")
def license_activate(request: ActivationRequest):
    result = activate(request.license, request.signature)
    if not result.get("active"):
        reason = result.get("reason", "ACTIVATION_FAILED")
        code = 503 if reason.startswith("LICENSE_PUBLIC_KEY_") else 400
        raise HTTPException(status_code=code, detail=reason)
    return result
