"""phase 8: analytics SQL views

Revision ID: 0005_analytics_views
Revises: 0004_feedback_review
Create Date: 2026-05-14

Creates materialized + regular views for Metabase dashboards.
Materialized views need REFRESH; we schedule that via Celery beat.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_analytics_views"
down_revision: Union[str, None] = "0004_feedback_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VIEWS_SQL = """
-- 1. v_daily_active_users — DAU per day, last 90 days
CREATE OR REPLACE VIEW v_daily_active_users AS
SELECT
    tenant_id,
    DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh') AS day,
    COUNT(DISTINCT conversation_id) AS active_conversations,
    COUNT(DISTINCT (SELECT user_id FROM conversations WHERE id = m.conversation_id)) AS dau,
    COUNT(*) FILTER (WHERE role = 'user') AS user_messages,
    COUNT(*) FILTER (WHERE role = 'assistant') AS bot_messages
FROM messages m
WHERE created_at > NOW() - INTERVAL '90 days'
GROUP BY tenant_id, DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh');

-- 2. v_monthly_active_users — MAU, last 12 months
CREATE OR REPLACE VIEW v_monthly_active_users AS
SELECT
    c.tenant_id,
    DATE_TRUNC('month', m.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh') AS month,
    COUNT(DISTINCT c.user_id) AS mau
FROM messages m
JOIN conversations c ON c.id = m.conversation_id
WHERE m.role = 'user'
  AND m.created_at > NOW() - INTERVAL '12 months'
GROUP BY c.tenant_id, DATE_TRUNC('month', m.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh');

-- 3. v_cost_per_day — daily LLM cost breakdown
CREATE OR REPLACE VIEW v_cost_per_day AS
SELECT
    tenant_id,
    DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh') AS day,
    model,
    COUNT(*) AS message_count,
    COALESCE(SUM(tokens_input), 0) AS tokens_in,
    COALESCE(SUM(tokens_output), 0) AS tokens_out,
    COALESCE(SUM(cost_usd), 0)::numeric(10,4) AS cost_usd,
    COUNT(*) FILTER (WHERE cached) AS cached_responses
FROM messages
WHERE role = 'assistant'
  AND created_at > NOW() - INTERVAL '90 days'
GROUP BY tenant_id, DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'), model;

-- 4. v_cost_per_user — cost per user (last 30 days)
CREATE OR REPLACE VIEW v_cost_per_user AS
SELECT
    u.tenant_id,
    u.id AS user_id,
    u.email,
    u.role,
    COUNT(m.id) AS message_count,
    COALESCE(SUM(m.tokens_input + m.tokens_output), 0) AS total_tokens,
    COALESCE(SUM(m.cost_usd), 0)::numeric(10,4) AS total_cost_usd,
    MAX(m.created_at) AS last_message_at
FROM users u
LEFT JOIN conversations c ON c.user_id = u.id
LEFT JOIN messages m ON m.conversation_id = c.id
    AND m.role = 'assistant'
    AND m.created_at > NOW() - INTERVAL '30 days'
GROUP BY u.tenant_id, u.id, u.email, u.role;

-- 5. v_csat — CSAT score over time
CREATE OR REPLACE VIEW v_csat AS
SELECT
    tenant_id,
    DATE_TRUNC('week', created_at AT TIME ZONE 'Asia/Ho_Chi_Minh') AS week,
    COUNT(*) AS total_feedback,
    COUNT(*) FILTER (WHERE rating = 1) AS thumbs_up,
    COUNT(*) FILTER (WHERE rating = -1) AS thumbs_down,
    ROUND(
        COUNT(*) FILTER (WHERE rating = 1)::numeric
        / NULLIF(COUNT(*), 0)::numeric,
        3
    ) AS csat
FROM feedback
WHERE created_at > NOW() - INTERVAL '90 days'
GROUP BY tenant_id, DATE_TRUNC('week', created_at AT TIME ZONE 'Asia/Ho_Chi_Minh');

-- 6. v_channel_breakdown — usage per channel
CREATE OR REPLACE VIEW v_channel_breakdown AS
SELECT
    c.tenant_id,
    c.channel,
    COUNT(DISTINCT c.id) AS conversations,
    COUNT(DISTINCT c.user_id) AS unique_users,
    COUNT(m.id) AS messages
FROM conversations c
LEFT JOIN messages m ON m.conversation_id = c.id
    AND m.created_at > NOW() - INTERVAL '30 days'
GROUP BY c.tenant_id, c.channel;

-- 7. v_unanswered_rate — proxy for KB gap (assistant said "tôi không biết" or similar)
CREATE OR REPLACE VIEW v_unanswered_rate AS
SELECT
    tenant_id,
    DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh') AS day,
    COUNT(*) AS total_assistant,
    COUNT(*) FILTER (
        WHERE content ILIKE '%không tìm thấy%'
           OR content ILIKE '%không có thông tin%'
           OR content ILIKE '%không biết%'
           OR content ILIKE '%don''t have%'
           OR content ILIKE '%no information%'
    ) AS unanswered,
    ROUND(
        COUNT(*) FILTER (WHERE content ILIKE '%không%')::numeric
        / NULLIF(COUNT(*), 0)::numeric,
        3
    ) AS unanswered_rate
FROM messages
WHERE role = 'assistant'
  AND created_at > NOW() - INTERVAL '30 days'
GROUP BY tenant_id, DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh');

-- 8. v_tool_usage — tool call breakdown
CREATE OR REPLACE VIEW v_tool_usage AS
SELECT
    tenant_id,
    DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh') AS day,
    tool_name,
    COUNT(*) AS calls,
    COUNT(*) FILTER (WHERE success) AS successful,
    COUNT(*) FILTER (WHERE NOT success) AS failed,
    ROUND(AVG(duration_ms)::numeric, 0) AS avg_duration_ms,
    ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)::numeric, 0) AS p95_duration_ms
FROM tool_audit
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY tenant_id, DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'), tool_name;

-- 9. v_moderation_summary — moderation event trends
CREATE OR REPLACE VIEW v_moderation_summary AS
SELECT
    tenant_id,
    DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh') AS day,
    event_type,
    severity,
    action_taken,
    COUNT(*) AS events
FROM moderation_events
WHERE created_at > NOW() - INTERVAL '90 days'
GROUP BY tenant_id, DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'),
         event_type, severity, action_taken;

-- 10. v_user_retention — 7-day rolling cohort retention
CREATE OR REPLACE VIEW v_user_retention AS
WITH cohorts AS (
    SELECT
        u.id AS user_id,
        u.tenant_id,
        DATE_TRUNC('week', u.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh') AS cohort_week
    FROM users u
    WHERE u.created_at > NOW() - INTERVAL '90 days'
),
activity AS (
    SELECT DISTINCT
        c.tenant_id,
        c.user_id,
        DATE_TRUNC('week', m.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh') AS active_week
    FROM messages m
    JOIN conversations c ON c.id = m.conversation_id
    WHERE m.role = 'user'
)
SELECT
    co.tenant_id,
    co.cohort_week,
    a.active_week,
    EXTRACT(WEEK FROM (a.active_week - co.cohort_week))::int AS week_offset,
    COUNT(DISTINCT co.user_id) AS users_active
FROM cohorts co
JOIN activity a ON a.user_id = co.user_id AND a.tenant_id = co.tenant_id
GROUP BY co.tenant_id, co.cohort_week, a.active_week;

-- 11. v_top_users_last_7d — leaderboard of most active users (last 7 days)
CREATE OR REPLACE VIEW v_top_users_last_7d AS
SELECT
    u.tenant_id,
    u.id AS user_id,
    u.email,
    u.role,
    COUNT(m.id) AS message_count,
    COALESCE(SUM(m.cost_usd), 0)::numeric(10,4) AS cost_usd_7d
FROM users u
JOIN conversations c ON c.user_id = u.id
JOIN messages m ON m.conversation_id = c.id
WHERE m.created_at > NOW() - INTERVAL '7 days'
  AND m.role = 'user'
GROUP BY u.tenant_id, u.id, u.email, u.role
ORDER BY message_count DESC;

-- 12. v_funnel_signup_to_active — signup → first message → 2nd → 7d retained
CREATE OR REPLACE VIEW v_funnel_signup_to_active AS
WITH stages AS (
    SELECT
        u.id AS user_id,
        u.tenant_id,
        u.created_at AS signup_at,
        MIN(m.created_at) FILTER (WHERE m.role = 'user') AS first_msg_at,
        COUNT(DISTINCT DATE(m.created_at)) FILTER (WHERE m.role = 'user') AS active_days
    FROM users u
    LEFT JOIN conversations c ON c.user_id = u.id
    LEFT JOIN messages m ON m.conversation_id = c.id
    GROUP BY u.id, u.tenant_id, u.created_at
)
SELECT
    tenant_id,
    DATE_TRUNC('week', signup_at) AS cohort,
    COUNT(*) AS signed_up,
    COUNT(*) FILTER (WHERE first_msg_at IS NOT NULL) AS sent_first_message,
    COUNT(*) FILTER (WHERE active_days >= 2) AS sent_second_message,
    COUNT(*) FILTER (WHERE active_days >= 7) AS retained_7d
FROM stages
WHERE signup_at > NOW() - INTERVAL '12 weeks'
GROUP BY tenant_id, DATE_TRUNC('week', signup_at);
"""


def upgrade() -> None:
    for stmt in VIEWS_SQL.split(";"):
        s = stmt.strip()
        if s:
            op.execute(s)


def downgrade() -> None:
    views = [
        "v_funnel_signup_to_active",
        "v_top_users_last_7d",
        "v_user_retention",
        "v_moderation_summary",
        "v_tool_usage",
        "v_unanswered_rate",
        "v_channel_breakdown",
        "v_csat",
        "v_cost_per_user",
        "v_cost_per_day",
        "v_monthly_active_users",
        "v_daily_active_users",
    ]
    for v in views:
        op.execute(f"DROP VIEW IF EXISTS {v}")
