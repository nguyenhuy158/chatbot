# Chatbot Roadmap

Status: scaffold imported (9 phases stubbed). This roadmap drives the path from scaffold → running pilot → production.

Reference docs:
- `docs/architecture/chatbot-architecture-v0.2.md` — design of record
- `docs/architecture/SCAFFOLD-README.md` — module map
- `docs/runbooks/docker-hardening.md` — prod hardening checklist

---

## M0 — Bootstrap (1–2 days)

**Goal:** local dev stack boots, smoke tests pass.

- [ ] `pip install -e .[dev]`
- [ ] Copy `.env.example` → `.env`; fill `OPENAI_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, `GOOGLE_OAUTH_CLIENT_ID/SECRET`
- [ ] `docker compose up -d postgres redis qdrant`
- [ ] `alembic upgrade head`
- [ ] `pytest tests/test_smoke.py` green
- [ ] GitHub Actions: lint (ruff) + test on PR

**Exit:** `make up` boots clean, smoke tests pass in CI.

---

## M1 — Core chat verified (3–5 days)

**Goal:** real end-to-end chat with auth + LLM, no mocks on hot path.

- [ ] Wire `app/services/llm_gateway.py` to OpenAI/Anthropic with real keys
- [ ] Drop placeholder code in `app/db/base.py:15`, `app/db/models/document.py:23`
- [ ] E2E manual test: Google OAuth login → POST `/api/chat` → streamed answer
- [ ] Add Sentry SDK init in `app/core/telemetry.py`
- [ ] Structured JSON logs via `app/core/logging.py`

**Exit:** demo chat in browser via Chainlit UI against real LLM.

---

## M2 — RAG on real data (1 week)

**Goal:** retrieval + citation correct over pilot corpus.

- [ ] Implement `app/workers/ingestion.py:10` (parse → chunk → embed → store)
- [ ] Run `scripts/ingest.py` against pilot corpus (FAQ + policy PDFs)
- [ ] `tests/test_rag.py` green against live Qdrant index
- [ ] Tune `app/rag/reranker.py` thresholds (recall@5 ≥ 0.85 on golden set)
- [ ] Citation rendering in Chainlit UI (clickable source chips)

**Exit:** golden RAG eval ≥ target on `evals/golden/rag.yaml`.

---

## M3 — Agent + memory hardening (1 week)

**Goal:** agent graph robust; memory + guardrails proven.

- [ ] Expand `app/agent/graph.py` nodes: tool routing, fallback, retry-with-backoff
- [ ] Fill `app/services/reputation.py:94` — query `moderation_events` for prior bans
- [ ] Fill `app/channels/telegram.py:115` — close conversation row on /reset
- [ ] PII redaction sanity (`app/memory/pii.py`) on VN ID/phone patterns
- [ ] Guardrails: `tests/test_guardrails.py` green; OpenAI moderation + VN patterns wired

**Exit:** chaos test (bad input, tool timeout, retrieval miss) handled gracefully.

---

## M4 — Eval gate (3 days)

**Goal:** automated quality regression detection.

- [ ] Run `python -m app.eval.cli` over all 5 golden YAMLs (faq, tools, rag, guardrails, multilang)
- [ ] Persist baseline scores; CI fails on regression > X%
- [ ] Admin eval dashboard (`app/api/admin_eval.py`) usable

**Exit:** PR blocked automatically when golden score drops.

---

## M5 — Channels live (1 week)

**Goal:** Slack + Telegram in pilot.

- [ ] Slack: socket mode in dev, events API + signing secret in prod
- [ ] Telegram: webhook + HTTPS endpoint
- [ ] Per-channel rate limits via `app/services/quota.py`
- [ ] `tests/test_channels.py` green

**Exit:** pilot users chatting from Slack + Telegram against same backend.

---

## M6 — Admin + analytics (3–5 days)

**Goal:** ops can see usage; admin can act.

- [ ] Metabase wired to `alembic/versions/0005_analytics_views.py` views
- [ ] Daily email report via `app/workers/scheduled.py` + `app/analytics/email_reporter.py`
- [ ] Admin ban/unban (`app/api/admin_actions.py`) end-to-end tested
- [ ] Feedback loop: thumbs in UI → `app/api/feedback.py` → review queue

**Exit:** ops dashboard shows DAU, token spend, top intents, error rate.

---

## M7 — Production deploy (1 week)

**Goal:** secure, reproducible prod.

- [ ] Full pass of `docs/runbooks/docker-hardening.md`
- [ ] `make docker-scan` (Trivy) clean — no HIGH/CRITICAL
- [ ] TLS reverse proxy (Caddy or Traefik) in front of FastAPI
- [ ] Secrets via SOPS, Vault, or cloud KMS — not `.env` files
- [ ] Backup + restore drill per `docs/runbooks/restore.md`
- [ ] `docker-compose.prod.yml` deployed to staging, then prod

**Exit:** prod live, SLO defined, backup proven.

---

## M8 — Observability (3 days)

**Goal:** can debug a bad answer in production.

- [ ] OpenTelemetry traces: LLM call, RAG retrieve, tool invocation spans
- [ ] Dashboards: token spend, p50/p95 latency, error rate by route
- [ ] Alerts: error rate > X%, p95 > Y s, daily token spend > $Z, quota breach spike

**Exit:** on-call can trace any user message ID to LLM/RAG/tool spans.

---

## Cross-cutting

- **Security:** monthly `scripts/security-scan.sh`; rotate API keys quarterly
- **Cost:** weekly token spend review; cache hit rate tracked (`app/services/cache.py`)
- **Docs:** every feature lands with runbook entry in `docs/runbooks/`

## Open TODOs in code (grep-derived)

| File:Line | Item |
|---|---|
| `app/workers/ingestion.py:10` | Implement Phase 2 ingestion pipeline |
| `app/services/reputation.py:94` | Query `moderation_events` for prior_bans |
| `app/channels/telegram.py:115` | Mark conversation closed on /reset |
| `app/db/base.py:15` | Empty `pass` — confirm intended |
| `app/db/models/document.py:23` | Empty `pass` — confirm intended |
