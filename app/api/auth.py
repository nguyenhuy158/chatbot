"""SSO authentication: Google + Microsoft."""
from uuid import uuid4

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DbSession
from app.core.exceptions import AuthError
from app.core.security import create_access_token, create_refresh_token
from app.db.models import User

router = APIRouter()

oauth = OAuth()

if settings.GOOGLE_CLIENT_ID:
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

if settings.MICROSOFT_CLIENT_ID:
    oauth.register(
        name="microsoft",
        client_id=settings.MICROSOFT_CLIENT_ID,
        client_secret=settings.MICROSOFT_CLIENT_SECRET,
        server_metadata_url=(
            f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}"
            "/v2.0/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid email profile"},
    )


@router.get("/login/{provider}")
async def login(provider: str, request: Request):
    if provider not in ("google", "microsoft"):
        raise AuthError(f"Unknown provider: {provider}")
    client = oauth.create_client(provider)
    redirect_uri = f"{settings.APP_BASE_URL}/auth/callback/{provider}"
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/callback/{provider}")
async def callback(provider: str, request: Request, db: DbSession):
    client = oauth.create_client(provider)
    try:
        token = await client.authorize_access_token(request)
    except OAuthError as e:
        raise AuthError(f"OAuth failed: {e}")

    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email")
    name = userinfo.get("name")
    subject = userinfo.get("sub")

    if not email:
        raise AuthError("No email in OAuth response")

    # Upsert user
    result = await db.execute(
        select(User).where(
            User.email == email,
            User.tenant_id == settings.DEFAULT_TENANT_ID,
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        # Decide role: simple heuristic — internal email domain → internal
        role = "internal" if email.endswith("@techcoop.vn") else "external"
        user = User(
            id=uuid4(),
            tenant_id=settings.DEFAULT_TENANT_ID,
            email=email,
            name=name,
            role=role,
            sso_provider=provider,
            sso_subject=subject,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access = create_access_token(user.id, user.role, user.tenant_id)
    refresh = create_refresh_token(user.id, user.tenant_id)

    response = RedirectResponse(url="/")
    response.set_cookie(
        "access_token",
        access,
        httponly=True,
        secure=settings.APP_ENV == "prod",
        samesite="lax",
        max_age=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        "refresh_token",
        refresh,
        httponly=True,
        secure=settings.APP_ENV == "prod",
        samesite="lax",
        max_age=settings.JWT_REFRESH_EXPIRE_DAYS * 86400,
    )
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response
