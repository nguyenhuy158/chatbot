"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api import (
    admin,
    admin_actions,
    admin_analytics,
    admin_eval,
    auth,
    chat,
    documents,
    feedback,
    images,
    memories,
    onboarding,
    user,
)
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.telemetry import setup_telemetry
from app.db.session import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    setup_logging()
    setup_telemetry(app)
    await init_db()
    # Mount channels if configured
    from app.channels.slack import mount_slack
    from app.channels.telegram import mount_telegram
    mount_slack(app)
    await mount_telegram(app)
    yield
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    debug=settings.APP_DEBUG,
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_DEBUG else None,
    redoc_url="/redoc" if settings.APP_DEBUG else None,
)

# Middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.APP_SECRET_KEY,
    https_only=settings.APP_ENV == "prod",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
register_exception_handlers(app)

# Routes
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(images.router, prefix="/api/images", tags=["images"])
app.include_router(feedback.router, prefix="/api", tags=["feedback"])
app.include_router(user.router, prefix="/api/me", tags=["user"])
app.include_router(onboarding.router, prefix="/api/me", tags=["onboarding"])
app.include_router(memories.router, prefix="/api/me", tags=["memory"])
app.include_router(admin_actions.router, prefix="/api", tags=["admin-actions"])
app.include_router(admin_eval.router, prefix="/api", tags=["admin-eval"])
app.include_router(admin_analytics.router, prefix="/api", tags=["admin-analytics"])

# Admin panel (mounted separately)
admin.setup_admin(app)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": settings.APP_NAME,
        "docs": "/docs",
        "health": "/health",
    }
