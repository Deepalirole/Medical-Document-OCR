from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, Header
from jwt import PyJWKClient

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.repositories.base import Repository
from app.repositories.supabase.client import SupabaseRestClient
from app.repositories.supabase.repository import SupabaseRepository


@dataclass(frozen=True)
class AuthContext:
    user_id: UUID
    email: str | None
    access_token: str


async def _verify_with_user_endpoint(token: str, settings: Settings) -> dict:
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        response = await client.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={
                "apikey": settings.supabase_publishable_key,
                "Authorization": f"Bearer {token}",
            },
        )
    if response.status_code != 200:
        raise AppError("AUTHENTICATION_FAILED", "Invalid or expired session.", 401)
    return response.json()


async def authenticate_token(token: str, settings: Settings) -> AuthContext:
    if not settings.supabase_configured:
        raise AppError("SERVICE_NOT_CONFIGURED", "Supabase authentication is not configured.", 503)

    payload: dict
    algorithm = str(jwt.get_unverified_header(token).get("alg", ""))
    if algorithm not in {"RS256", "ES256"}:
        payload = await _verify_with_user_endpoint(token, settings)
    else:
        try:
            jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            signing_key = PyJWKClient(jwks_url, cache_keys=True).get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience=settings.supabase_jwt_audience,
                options={"require": ["exp", "sub"]},
            )
        except Exception:
            payload = await _verify_with_user_endpoint(token, settings)

    subject = payload.get("sub") or payload.get("id")
    if not subject:
        raise AppError("AUTHENTICATION_FAILED", "Session has no user identity.", 401)
    return AuthContext(user_id=UUID(subject), email=payload.get("email"), access_token=token)


async def get_auth_context(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("AUTHENTICATION_REQUIRED", "A bearer session is required.", 401)
    return await authenticate_token(authorization.removeprefix("Bearer ").strip(), settings)


def get_repository(
    auth: AuthContext = Depends(get_auth_context), settings: Settings = Depends(get_settings)
) -> Repository:
    return SupabaseRepository(SupabaseRestClient(settings, auth.access_token))


AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
RepoDep = Annotated[Repository, Depends(get_repository)]
