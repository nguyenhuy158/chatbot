"""Admin analytics endpoints — read-only views over Postgres SQL views."""
from fastapi import APIRouter, Query

from app.analytics import queries
from app.core.deps import AdminUser, DbSession

router = APIRouter()


@router.get("/admin/analytics/dau")
async def get_dau(admin: AdminUser, db: DbSession, days: int = Query(30, ge=1, le=90)):
    return await queries.dau_last_n_days(db, admin.tenant_id, days)


@router.get("/admin/analytics/cost/summary")
async def get_cost_summary(admin: AdminUser, db: DbSession, days: int = Query(30, ge=1, le=90)):
    return await queries.cost_summary(db, admin.tenant_id, days)


@router.get("/admin/analytics/cost/daily")
async def get_cost_daily(admin: AdminUser, db: DbSession, days: int = Query(14, ge=1, le=90)):
    return await queries.cost_by_day(db, admin.tenant_id, days)


@router.get("/admin/analytics/cost/top-users")
async def get_top_users(admin: AdminUser, db: DbSession, limit: int = Query(20, ge=1, le=100)):
    return await queries.top_users_by_cost(db, admin.tenant_id, limit)


@router.get("/admin/analytics/csat")
async def get_csat(admin: AdminUser, db: DbSession, weeks: int = Query(12, ge=1, le=52)):
    return await queries.csat_weekly(db, admin.tenant_id, weeks)


@router.get("/admin/analytics/channels")
async def get_channels(admin: AdminUser, db: DbSession):
    return await queries.channel_breakdown(db, admin.tenant_id)


@router.get("/admin/analytics/tools")
async def get_tools(admin: AdminUser, db: DbSession, days: int = Query(7, ge=1, le=30)):
    return await queries.tool_usage(db, admin.tenant_id, days)


@router.get("/admin/analytics/funnel")
async def get_funnel(admin: AdminUser, db: DbSession):
    return await queries.funnel(db, admin.tenant_id)


@router.get("/admin/analytics/moderation")
async def get_moderation(admin: AdminUser, db: DbSession, days: int = Query(30, ge=1, le=90)):
    return await queries.moderation_summary(db, admin.tenant_id, days)


@router.post("/admin/analytics/send-cost-report")
async def trigger_cost_report(admin: AdminUser):
    """Manually trigger the daily cost report (skips waiting for cron)."""
    from app.workers.scheduled import _send_cost_report_async
    result = await _send_cost_report_async()
    return {"status": result}
