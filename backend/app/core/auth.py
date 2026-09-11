from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings

bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    subject: str
    username: str
    email: str | None
    roles: set[str]


@lru_cache(maxsize=1)
def _jwks() -> dict:
    response = httpx.get(settings.keycloak_jwks_url, timeout=10.0)
    response.raise_for_status()
    return response.json()


def _decode_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        keys = _jwks().get("keys", [])
        key = next((k for k in keys if k.get("kid") == kid), None)
        if key is None:
            _jwks.cache_clear()
            keys = _jwks().get("keys", [])
            key = next((k for k in keys if k.get("kid") == kid), None)
        if key is None:
            raise HTTPException(status_code=401, detail="Unknown token signing key")

        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.keycloak_issuer,
            options={"verify_aud": False},
        )
        if claims.get("azp") != settings.keycloak_web_client_id:
            raise HTTPException(status_code=401, detail="Token client is not allowed")
        return claims
    except HTTPException:
        raise
    except (JWTError, httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> CurrentUser:
    if not settings.auth_required:
        return CurrentUser(
            subject="dev-local",
            username="dev-local",
            email=None,
            roles={"SYSTEM_ADMIN"},
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = _decode_token(credentials.credentials)
    realm_roles = set((claims.get("realm_access") or {}).get("roles") or [])
    return CurrentUser(
        subject=str(claims.get("sub", "")),
        username=str(claims.get("preferred_username", "")),
        email=claims.get("email"),
        roles=realm_roles,
    )


def require_roles(*allowed: str) -> Callable:
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not (user.roles & set(allowed)):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user
    return dependency
