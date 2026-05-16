# Metabase Setup

Metabase is included in `docker-compose.yml` on port 3000. After first start:

## 1. Connect to Postgres

1. Open http://localhost:3000
2. Create admin account
3. Add database:
   - Type: PostgreSQL
   - Name: `Chatbot`
   - Host: `postgres` (service name in docker network)
   - Port: `5432`
   - Database: `chatbot`
   - User: `chatbot`
   - Password: `chatbot`

## 2. Recommended dashboards

Create one dashboard per topic. SQL queries below — paste each into Metabase as a Question
(Native query), name it, save to a collection.

### Dashboard: "Executive Summary"

**Q1: DAU last 30 days (line chart)**
```sql
SELECT day, dau FROM v_daily_active_users
WHERE day >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY day;
```

**Q2: Cost last 30 days (line chart)**
```sql
SELECT day, SUM(cost_usd) AS cost_usd
FROM v_cost_per_day
WHERE day >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY day ORDER BY day;
```

**Q3: CSAT trend (line chart)**
```sql
SELECT week, csat FROM v_csat ORDER BY week;
```

**Q4: Channel breakdown (pie)**
```sql
SELECT channel, messages FROM v_channel_breakdown ORDER BY messages DESC;
```

### Dashboard: "Cost Deep Dive"

**Q5: Cost by model (stacked bar)**
```sql
SELECT day, model, SUM(cost_usd) AS cost
FROM v_cost_per_day
WHERE day >= CURRENT_DATE - INTERVAL '14 days'
GROUP BY day, model ORDER BY day;
```

**Q6: Top 20 users by cost (table)**
```sql
SELECT email, role, message_count, total_cost_usd
FROM v_cost_per_user
ORDER BY total_cost_usd DESC NULLS LAST
LIMIT 20;
```

**Q7: Cache hit rate (number)**
```sql
SELECT
  ROUND(SUM(cached_responses)::numeric / NULLIF(SUM(message_count), 0) * 100, 1) AS cache_pct
FROM v_cost_per_day
WHERE day >= CURRENT_DATE - INTERVAL '7 days';
```

### Dashboard: "Quality"

**Q8: CSAT by week (line)**
```sql
SELECT week, csat, total_feedback FROM v_csat ORDER BY week;
```

**Q9: Tool success rate (table)**
```sql
SELECT tool_name,
       SUM(calls) AS total,
       ROUND(SUM(successful)::numeric / NULLIF(SUM(calls), 0) * 100, 1) AS success_pct,
       AVG(avg_duration_ms) AS avg_ms
FROM v_tool_usage
WHERE day >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY tool_name ORDER BY total DESC;
```

**Q10: Unanswered rate (line)**
```sql
SELECT day, unanswered_rate FROM v_unanswered_rate ORDER BY day;
```

### Dashboard: "Growth"

**Q11: Funnel last 12 weeks (funnel chart)**
```sql
SELECT
  'signed_up' AS step, SUM(signed_up) AS users FROM v_funnel_signup_to_active
UNION ALL
SELECT 'first_message', SUM(sent_first_message) FROM v_funnel_signup_to_active
UNION ALL
SELECT 'second_message', SUM(sent_second_message) FROM v_funnel_signup_to_active
UNION ALL
SELECT '7d_retained', SUM(retained_7d) FROM v_funnel_signup_to_active;
```

**Q12: Retention cohort heatmap (pivot)**
```sql
SELECT cohort_week, week_offset, SUM(users_active) AS users
FROM v_user_retention
GROUP BY cohort_week, week_offset
ORDER BY cohort_week, week_offset;
```

### Dashboard: "Security & Moderation"

**Q13: Moderation events daily (stacked bar)**
```sql
SELECT day, event_type, SUM(events) AS events
FROM v_moderation_summary
WHERE day >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY day, event_type ORDER BY day;
```

**Q14: Top offenders (table)**
```sql
SELECT user_id, COUNT(*) AS events, SUM((severity = 'high')::int) AS high_severity
FROM moderation_events
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY user_id ORDER BY high_severity DESC, events DESC LIMIT 20;
```

## 3. Set up scheduled refresh

Metabase will hit the views every dashboard load. For very expensive ones,
turn them into materialized views and add a Celery beat task to `REFRESH`.

## 4. Alerts via Metabase

For cost spikes: Metabase → Question → "Alert me when..." → cost > $X.
Email or Slack webhook.

## 5. Access control

Restrict Metabase to internal email domains via SSO (Metabase Enterprise)
or by binding to a VPN-only port.
