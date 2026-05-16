"""FastAPI dependencies."""
from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError, ForbiddenError
from app.core.security import decode_token
from app.db.session import get_db


class CurrentUser:
    """Authenticated user context from JWT."""

    def __init__(self, user_id: UUID, role: str, tenant_id: UUID):
        self.user_id = user_id
        self.role = role
        self.tenant_id = tenant_id

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_internal(self) -> bool:
        return self.role in ("internal", "admin")


async def get_current_user(access_token: str | None = Cookie(None)) -> CurrentUser:
    if not access_token:
        raise AuthError("Not authenticated")

    payload = decode_token(access_token)
    if payload.get("type") != "access":
        raise AuthError("Invalid token type")

    return CurrentUser(
        user_id=UUID(payload["sub"]),
        role=payload["role"],
        tenant_id=UUID(payload["tenant_id"]),
    )


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise ForbiddenError("Admin role required")
    return user


DbSession = Annotated[AsyncSession, Depends(get_db)]
User = Annotated[CurrentUser, Depends(get_current_user)]
AdminUser = Annotated[CurrentUser, Depends(require_admin)]
