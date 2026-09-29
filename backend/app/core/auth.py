from dataclasses import dataclass, field
from functools import lru_cache
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings


bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class CurrentUser:
    firebase_uid: str
    email: str
    id_usuario: int | None = None
    id_organizacao: int | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)
    clinic_ids: frozenset[int] = field(default_factory=frozenset)


@lru_cache
def _firebase_app():
    from firebase_admin import credentials, get_app, initialize_app
    try:
        return get_app()
    except ValueError:
        options = {"projectId": settings.firebase_project_id} if settings.firebase_project_id else None
        return initialize_app(credentials.ApplicationDefault(), options=options)


def create_firebase_user(email: str, password: str, display_name: str):
    from firebase_admin import auth
    return auth.create_user(email=email, password=password, display_name=display_name, app=_firebase_app())


def delete_firebase_user(uid: str) -> None:
    from firebase_admin import auth
    auth.delete_user(uid, app=_firebase_app())


def reset_firebase_password(uid: str, password: str) -> None:
    from firebase_admin import auth
    auth.update_user(uid, password=password, app=_firebase_app())


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if settings.auth_disabled:
        return CurrentUser("development", "dev@local", permissions=frozenset({"*"}))
    if not credentials or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de autenticação ausente")
    try:
        from firebase_admin import auth
        decoded = auth.verify_id_token(
            credentials.credentials,
            app=_firebase_app(),
            check_revoked=True,
            clock_skew_seconds=settings.firebase_clock_skew_seconds,
        )
    except Exception as exc:
        # Never log the credential itself. The exception type is needed to
        # distinguish an invalid token from clock, certificate or ADC failures.
        logger.warning("Firebase token verification failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de autenticação inválido") from exc
    if not decoded.get("email"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Conta sem e-mail verificado no token")
    return CurrentUser(decoded["uid"], decoded["email"].strip().lower())


def require_permissions(*required: str):
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if "*" not in user.permissions and not set(required).issubset(user.permissions):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permissão insuficiente")
        return user
    return dependency
