# Detailed Execution Plan

Companion to `docs/ROADMAP.md`. Fills gaps left by milestone-level roadmap.
Status: scaffold, 3 commits, working tree clean. Nothing booted yet.

---

## Part A — Gaps in existing ROADMAP

### A.0 M0 Bootstrap — missing items
- Pin Python (3.12.x) via `.python-version` + Docker base image match
- Generate `requirements.lock` (pip-tools or uv) — `pyproject.toml` only has ranges
- Pre-commit hooks: ruff, ruff-format, mypy, trailing-whitespace, end-of-file-fixer, detect-secrets
- Verify `make up` target works (Makefile present but untested)
- Confirm Alembic head matches model definitions (`alembic check`)
- Health probes wired to `docker-compose.yml` (healthcheck blocks)
- `.env.example` lint: every var referenced in `app/core/config.py` present
- Smoke test must cover: startup lifespan, DB connect, Redis ping, Qdrant ping

### A.1 M1 Core chat — missing items
- LLM provider selection policy: primary + fallback + per-route override
- Streaming token test (SSE keepalive, client disconnect mid-stream)
- Google OAuth: redirect URI per env, state/nonce CSRF, refresh token storage
- Rate limit on `/api/chat` BEFORE auth (anti-abuse) vs after (per-user)
- Request/response logging redaction (no prompts in plaintext logs)
- Token accounting: count input+output per message → `usage_events` row
- LLM error taxonomy: rate-limit, context-overflow, content-filter, timeout, 5xx

### A.2 M2 RAG — missing items
- Corpus inventory: source list, owner, refresh cadence, license
- Chunking strategy: size, overlap, semantic boundary heuristic, table handling
- Embedding model lock: name + dimension + provider; migration path if changed
- Dedup: content hash before insert; near-dup via cosine threshold
- Ingestion concurrency + backpressure (Celery worker count, queue size)
- Re-index runbook: full rebuild vs incremental
- Citation format spec: source title + page/section + URL + chunk_id
- Eval methodology: golden set construction, inter-annotator agreement, refresh policy

### A.3 M3 Agent + memory — missing items
- Tool registry spec: name, input schema, output schema, side-effect class, timeout, retry
- Tool authorization matrix (which user role can invoke which tool)
- Prompt template versioning + A/B
- Memory schema versioning + migration (mem0 backing store)
- PII policy: detect-only vs redact vs block; per-channel override
- Conversation TTL + archival
- Reset semantics (per-channel /reset behavior table)

### A.4 M4 Eval gate — missing items
- Per-metric regression thresholds (not single X%)
- Eval dataset versioning (git-pinned, hash in CI artifact)
- Drift detection: production prompts diverge from golden distribution
- Human review queue for low-confidence eval items
- Cost ceiling per eval run (CI budget)

### A.5 M5 Channels — missing items
- Slack signing secret verification middleware
- Telegram webhook secret token
- Deduplication of repeated events (Slack retries, Telegram updates)
- Message idempotency key (channel_msg_id) — DB unique constraint
- Outbound reply queue with retry + dead-letter
- Per-channel feature flag (disable RAG on Telegram if needed)
- Threading model: Slack thread_ts ↔ conversation_id mapping
- File/image upload size + MIME allowlist per channel

### A.6 M6 Admin + analytics — missing items
- Metabase auth (SSO or shared secret), read-only DB role
- Admin role hierarchy: viewer / moderator / superadmin
- Audit log table for every admin action (who, when, what, before/after)
- Feedback workflow: thumb-down → review queue → resolution status
- Email deliverability: SPF/DKIM/DMARC, bounce handling
- Daily report content spec (metrics list + sample)

### A.7 M7 Production deploy — missing items
- **Deployment target decision** (cloud provider, VPS, k8s?) — currently undefined
- CI/CD pipeline: build → scan → push → deploy → smoke → rollback gate
- Image registry choice + retention
- Secret management choice (SOPS vs Vault vs cloud KMS) — pick one
- Database migration policy: pre-deploy vs post-deploy, expand-contract for breaking
- Zero-downtime deploy strategy (blue-green / rolling / canary)
- Backup target: where, encryption, retention, restore drill cadence
- DNS, TLS cert source (Let's Encrypt automation)
- Resource sizing: CPU/RAM per service, autoscale rules

### A.8 M8 Observability — missing items
- **SLO numbers** (currently placeholders): p95 latency, availability %, error budget
- Log retention period + storage tier
- Trace sampling rate (cost vs coverage)
- PII scrubbing in traces + logs
- On-call rotation, paging policy, runbook links from alerts
- Synthetic monitoring (health probe from outside)

---

## Part B — Topics ROADMAP omits entirely

### B.1 Security
- **Threat model** doc (STRIDE per component): auth, chat, RAG, admin, channels
- AuthN: session lifetime, refresh strategy, logout-everywhere
- AuthZ: role matrix, ownership checks on every resource endpoint
- Input validation: pydantic strict mode, max body size, max chat history depth
- Output filtering: prompt-injection mitigation, jailbreak detection
- Secret rotation runbook (quarterly per ROADMAP — but no procedure)
- Dependency scanning: Trivy in CI + scheduled rescan of deployed image
- SBOM generation per release
- Pen-test scope + cadence
- Incident response runbook (detect → contain → eradicate → recover → postmortem)

### B.2 Data governance
- Data classification: public / internal / PII / sensitive
- Retention policy per class (conversations, embeddings, logs, telemetry)
- Right-to-delete (user data export + erase endpoint)
- VN data residency (decree on personal data protection — confirm scope)
- Cross-border transfer (LLM provider in US/EU) — disclosure + consent
- Backup encryption at rest + in transit
- Access log for sensitive tables

### B.3 Cost engineering
- Per-user token budget + hard cap
- Per-route model tier (cheap model for FAQ, premium for complex)
- Cache hit rate target (semantic cache + exact cache)
- Embedding batch cost amortization
- Daily/monthly spend alert thresholds
- Cost attribution: per-tenant, per-feature, per-channel

### B.4 Reliability
- DR plan: RPO/RTO targets per service
- Failover strategy: DB replica, Redis sentinel, Qdrant snapshot
- Chaos drills: kill-pod, fill-disk, network-partition, LLM-provider-down
- Graceful degradation matrix (what works if LLM down? RAG down? DB down?)
- Circuit breakers around every external call (LLM, search, embedding)
- Idempotent retries with exponential backoff + jitter (verify everywhere)

### B.5 Performance
- Load test plan (k6 or locust): RPS target, ramp profile, soak duration
- Caching layers: HTTP, semantic, embedding, DB query
- Async-everything audit (no sync I/O in request path)
- Connection pool sizing (DB, Redis, HTTP clients)
- Cold-start budget (lifespan startup time)

### B.6 Quality + release
- Feature flag system (LaunchDarkly / Unleash / custom?) — pick one
- A/B testing infra (prompt variants, model variants)
- Canary release procedure
- Rollback procedure (DB schema, app version, prompt version)
- Changelog automation tied to Conventional Commits

### B.7 Compliance
- VN Personal Data Protection Decree compliance checklist
- Terms of service + privacy policy authored + linked from UI
- Cookie consent (if web UI uses cookies beyond session)
- LLM provider DPA review (OpenAI, Anthropic, Google)
- Logging of consent events

### B.8 Multi-tenancy (decide now)
- Single tenant pilot only? Or multi-tenant from day 1?
- Decision affects: schema (tenant_id everywhere), auth, rate limits, billing, eval

### B.9 Internationalization
- `app/i18n/` exists — strategy doc: source-of-truth strings, translation flow, fallback
- LLM response language detection + steering
- Date/number/currency formatting per locale

### B.10 Developer experience
- Local dev story: hot reload, test DB seed, fixture corpus
- ADR (architecture decision record) practice — start log
- Onboarding doc for new dev (clone → run → first PR < 1 day)
- Style guide beyond ruff (naming, layering, error handling patterns)

### B.11 Feature flags

**Goal:** runtime toggles for model, RAG, tools, channels, guardrails — no redeploy. Targeting by tenant/user/channel/role/% rollout. Kill-switch + A/B + audit.

**Decision:** DIY Postgres + Redis cache (recommend). Vendor options (LaunchDarkly/Statsig SaaS, Unleash/GrowthBook self-host) deferred until scale demands. See Decision #6.

**Data model** (Alembic migration in M5 window):
- `feature_flags(key PK, type, default_value JSONB, description, owner, version, ts)` — type ∈ bool|string|int|json|percent
- `flag_rules(id, flag_key FK, priority, match JSONB, rollout_pct, value JSONB, enabled)` — eval order: priority → match → bucket → default
- `flag_audit(id, flag_key, actor, action, before, after, ts)` — retention 90d → archive

**Service layer** — `app/core/feature_flags.py`:
- `FlagContext(tenant_id, user_id, channel, role, env)` built in request middleware
- `FlagService.get_bool/get_str/get_json/variant(key, ctx, default)`
- Cache: Redis `flag:{key}` TTL 30s + pub/sub `flag:invalidate` for instant flush
- In-process LRU 5s on hot path → p99 < 1ms
- Stale-on-error: last-known value, never raise

**Integration matrix:**

| Module | Flag keys |
|---|---|
| `services/llm_gateway.py` | `llm.model.primary`, `llm.model.fallback`, `llm.streaming` |
| `rag/*` | `rag.enabled` (per channel), `rag.reranker.threshold`, `rag.top_k` |
| `agent/graph.py` | `agent.tools.allowlist`, `agent.max_steps` |
| `guardrails/*` | `guardrails.moderation.enabled`, `guardrails.pii.mode` (off/detect/redact/block) |
| `channels/telegram.py` | `channel.telegram.enabled` (kill-switch) |
| `api/chat.py` | `chat.rate_limit.rpm`, `chat.maintenance_mode` |
| `workers/ingestion.py` | `ingest.embedding.model`, `ingest.batch_size` |

**Admin API** — `app/api/admin_flags.py` (role=admin):
- `GET /admin/flags`, `POST /admin/flags`, `PATCH /admin/flags/{key}`
- `POST /admin/flags/{key}/rules`, `DELETE /admin/flags/{key}/rules/{id}`
- `POST /admin/flags/{key}/evaluate` — dry-run for ctx
- `GET /admin/flags/{key}/audit`
- Phase-1 UI: Metabase view + httpie. Phase-2: React admin page.

**A/B + rollout:**
- Bucket = `xxhash(user_id + ":" + flag_key) % 100` — sticky per user
- Variant returns `"control"|"treatment"|...` + emits `experiment_exposure` event → analytics

**Safety rules:**
- Key namespaced `domain.subdomain.name`; type check on write
- Default value REQUIRED — fallback if service dies
- Critical flags tag `critical=true` → 2-admin approval (phase-2)
- Test override header `X-Flag-Override: key=value` only when `env=test`

**Testing:**
- Unit: rule matcher, percent bucket distribution (chi-square 10k samples)
- Integration: middleware ctx → flag eval → endpoint behavior
- Chaos: Redis down → fallback default, no 500
- Eval suite: snapshot flags pre-run, restore post-run

**Rollout steps** (~4–5 dev-days + 1 test-day, fit M5 window):
1. Migration + `FlagService` + Redis cache + first flag (`chat.maintenance_mode`)
2. Admin API + audit log + pytest coverage
3. Wire RAG + LLM model flags + kill-switches
4. Percent rollout + A/B variant + exposure events
5. Per-tenant rules + channel scoping
6. Metabase dashboard: flag state, exposure counts, audit trail

**Open questions:**
- Tenant schema chốt chưa? `flag_rules.match` cần `tenant_id` FK.
- GitOps flag-as-code YAML vs DB-only? Đề xuất DB-only phase-1.
- Audit retention 90d OK? Archive target?

**Dependencies:** B.8 multi-tenancy decision (rule schema), M5 channel work (per-channel scoping).

---

## Part C — Sequencing recommendation

Critical path before M0 done:
1. Decide deployment target (B.7 informs M7)
2. Decide secret management (informs M0, M7)
3. Decide multi-tenancy (B.8 informs schema — costly to retrofit)
4. Decide LLM provider strategy (informs M1, B.3)
5. Author threat model v0 (informs M0 CI, M7 hardening)

Then proceed M0 → M8 with each milestone's expanded checklist above.

---

## Part D — Decisions log (locked 2026-05-16)

| # | Decision | Chosen | Rationale |
|---|----------|--------|-----------|
| 1 | Deployment target | Single VPS + Docker Compose | Pilot < 50 user, < 500 msg/day. Cheap, simple, fast to ship. |
| 2 | Secret store | SOPS + age, encrypted files in git | No infra. Audit via git history. Rotate quarterly. |
| 3 | Tenancy | Single-tenant | Internal team only. No tenant_id columns. Document retrofit cost. |
| 4 | Primary LLM | Google Gemini (Flash for cheap routes, Pro for complex) | Cost fits $50/mo budget. Multimodal native. |
| 5 | Fallback LLM | OpenAI GPT-4o-mini | Cheap, fast, tool-calling parity. Trip on Gemini 5xx/429 or content-filter. |
| 6 | Feature flags | DIY (Postgres + Redis cache) | Tenant fit, audit log native, no vendor cost. |
| 7 | Lock tool | uv | Fast. `uv.lock` committed. Docker uses `uv pip sync`. |
| 8 | Vector store | Qdrant | Already in scaffold. Pilot scale fits single-node. |
| 9 | Pilot scale target | < 50 user, < 500 msg/day | VPS 2vCPU/4GB sizing. |
| 10 | Channels (pilot) | Web (Chainlit) + Slack + Telegram | All three M5 window. |
| 11 | Auth | Magic link / OTP via email | No Google OAuth dep. Allowlist via `users` table. |
| 12 | Eval gate | Block PR when any metric drops > 5% | Strict. Golden set must be stable first. |
| 13 | LLM budget cap | < $50/month | Daily alert at 80%. Hard cap = downgrade to Gemini Flash only. |
| 14 | Retention | Conversations + logs: 30d full, then anonymize (drop user_id, hash PII) | GDPR-aligned. Backup retention separate (90d). |
| 15 | Backup | Postgres `pg_dump` daily → S3/B2, encrypted, 90d retention | RPO 24h. Quarterly restore drill. |
| 16 | VN data residency | Soft. LLM US OK with DPA. Privacy policy discloses cross-border. | DPA review: OpenAI + Google. |
| 17 | Agent tools (pilot) | web_search (Tavily), calculator (asteval), gcal (read/create event) | Three only. Allowlist enforced. |
| 18 | SLO | p95 < 5s, availability 99% (≈ 7h/mo downtime budget) | Realistic pilot. Tighten post-M8. |
| 19 | PII policy | Redact before LLM via Presidio. VN ID + phone patterns added. | Token-substitution. Detect rate logged to audit. |
| 20 | Telemetry | Langfuse self-host (Docker compose service) | LLM trace + cost attribution. |
| 21 | Admin RBAC | superadmin > admin > moderator > viewer | Roles in `users.role`. Audit log all admin actions. |
| 22 | Slack depth | Bot + DM + @mention | No threads / interactive in pilot. |
| 23 | Telegram depth | Text + `/start`, `/reset`, `/help` | No media / inline buttons in pilot. |
| 24 | Ingestion sources | Order: admin upload → GDrive → crawler → API push | M2 admin upload only. GDrive M2.5. Crawler + API M5+. |
| 25 | Pre-commit | ruff + ruff-format + mypy strict + detect-secrets + conventional-commits | Installed before first M0 PR. |
| 26 | CI runner | GitHub Actions | `.github/` already present. |
| 27 | Email transport | Multi-provider chain: Postmark → Resend → Gmail SMTP | Setup all 3. Auto-fallback on send error. |
| 28 | Cache | Exact prompt + semantic + RAG result + embedding | All 4 layers. Redis backed. |
| 29 | Golden eval set | LLM-generate seed + human review filter | Start 20/category, grow to 50–100. Gemini for gen. |
| 30 | Multimodal | Skip pilot | Text only. Re-evaluate M6. |
| 31 | Onboarding | Interactive: bot self-intro + suggested prompts on first message | Use `app/api/onboarding.py`. |
| 32 | Repo workflow | Trunk-based + required PR review + green CI | Main branch protected. |
| 33 | Domain + TLS | Subdomain + Caddy auto TLS (Let's Encrypt) | Caddy container in compose. |

---

## Part E — Concrete spec per milestone (locked)

### E.0 M0 Bootstrap

**Dev environment**
- `.python-version` → `3.12`
- Install: `uv venv && uv pip install -e ".[dev]"`
- Generate lockfile: `uv lock` → commit `uv.lock`
- Docker base: `python:3.12-slim-bookworm`, multi-stage with `uv pip sync uv.lock`

**Pre-commit** (`.pre-commit-config.yaml`)
- ruff (lint) + ruff-format
- mypy --strict (incremental, app/ only first; expand later)
- detect-secrets (baseline `.secrets.baseline`)
- conventional-pre-commit (commit-msg hook)
- trailing-whitespace, end-of-file-fixer, check-yaml, check-toml

**Docker compose healthchecks**
- postgres: `pg_isready -U $POSTGRES_USER`
- redis: `redis-cli ping`
- qdrant: HTTP `GET /readyz`
- app: HTTP `GET /health`
- langfuse: HTTP `GET /api/public/health`

**Smoke test expansion** (`tests/test_smoke.py`)
- App startup lifespan succeeds
- DB `SELECT 1`
- Redis `PING`
- Qdrant collections list
- All Alembic migrations apply on fresh DB (`alembic upgrade head`)
- `alembic check` no drift

**SOPS setup**
- `.sops.yaml` config — age recipients for dev + prod
- `secrets/dev.enc.yaml`, `secrets/prod.enc.yaml`
- Pre-commit hook blocks committing decrypted secrets
- Document team key rotation in `docs/runbooks/secrets.md`

**CI workflow** (`.github/workflows/ci.yml`)
- Jobs: lint (ruff) → typecheck (mypy) → test (pytest with DB+Redis+Qdrant services) → security scan (trivy fs)
- Cache uv install
- Required on PR to main

**Exit criteria:** `make up` boots, smoke passes locally + CI, pre-commit hooks fire.

---

### E.1 M1 Core chat

**LLM gateway** (`app/services/llm_gateway.py`)
- Provider chain: Gemini primary → GPT-4o-mini fallback
- Trip fallback on: 429, 5xx, timeout > 30s, content-filter (non-policy), quota exceeded
- Per-route model override via feature flag `llm.model.<route>`
- Cost log per call: `usage_events(id, user_id, route, model, in_tokens, out_tokens, cost_usd, ts)`
- Error taxonomy enum: `RATE_LIMIT | CONTEXT_OVERFLOW | CONTENT_FILTER | TIMEOUT | UPSTREAM_5XX | UNKNOWN`

**Auth — Magic link / OTP**
- Replace Google OAuth scaffold endpoints
- Flow: `POST /auth/request` (email) → email with 6-digit OTP + magic link (token 15m TTL) → `POST /auth/verify` → session cookie (HttpOnly, Secure, SameSite=Lax)
- Allowlist check: email must exist in `users` table with `is_active=true`
- Rate limit: 5 OTP requests / 15m / email + IP

**Email transport chain** (`app/services/email.py`)
- Providers ordered: Postmark, Resend, Gmail SMTP
- Each call: try provider 1, on 5xx/network failure → provider 2 → provider 3
- Log `email_sends(provider, status, latency_ms, error)`
- Suppress retry on 4xx (bad address)

**Chat endpoint** (`app/api/chat.py`)
- SSE stream via `sse-starlette`
- Keepalive `: ping\n\n` every 15s
- Client disconnect → cancel LLM task (anyio cancel scope)
- Pre-auth rate limit (IP): 20 rpm
- Post-auth rate limit (user): 60 rpm (feature flag `chat.rate_limit.rpm`)

**Logging redaction**
- Custom structlog processor strips prompt content; logs hash + first 40 chars
- Full prompt + response written to `chat_messages` table (encrypted-at-rest via PG, app-layer optional)

**Exit:** Chainlit chat → magic-link auth → streamed Gemini answer → fallback verified by killing Gemini API key.

---

### E.2 M2 RAG

**Corpus inventory** (`docs/corpus.md`)
- Phase 1: admin-uploaded FAQ (markdown), HR policy PDFs, product docs from KB website (sync later)
- Owner per source, refresh cadence, license
- Status: collection plan — task list before M2 starts

**Chunking** — `app/rag/chunker.py`
- Strategy: semantic-recursive (LangChain-style), target 800 tokens, 100 overlap
- Tables: extract as markdown blocks, kept whole if ≤ 1200 tokens else row-windowed
- Heading hierarchy preserved in chunk metadata

**Embedding** — locked
- Model: `text-embedding-004` (Google) — 768 dim
- Migration policy: schema version field in `document_chunks.embedding_version`; reindex script if changed
- Batch: 100 chunks/call

**Dedup**
- `document_chunks.content_hash` (sha256) UNIQUE per source
- Near-dup: cosine > 0.97 → log + skip

**Ingestion pipeline** (`app/workers/ingestion.py:10`)
- Celery queue `ingest`, concurrency 2 on pilot VPS
- States: queued → parsing → chunking → embedding → indexed | failed
- Per-doc row in `documents(id, source_type, uri, status, error, ts)`

**Re-index runbook** (`docs/runbooks/reindex.md`)
- Full rebuild vs incremental
- Blue-green Qdrant collection: write to v2, swap alias, drop v1

**Eval methodology** (`evals/golden/rag.yaml`)
- 20 questions/category seed (LLM-gen via Gemini, human filter)
- Metrics: recall@5, MRR, citation correctness (manual rubric)
- Refresh quarterly

**Exit:** recall@5 ≥ 0.85 on golden, citation chips render in Chainlit.

---

### E.3 M3 Agent + memory + tools

**Tool registry** (`app/agent/tools/registry.py`)
- Schema per tool: name, input_schema (pydantic), output_schema, side_effect_class (read|write|external), timeout_s, retry_policy, allowlist_roles
- Pilot 3 tools:
  - `web_search` (Tavily, timeout 10s, retry 2x)
  - `calculator` (asteval, timeout 2s, no retry)
  - `gcal_event` (read + create, OAuth scope `calendar.events`, timeout 15s)

**Authorization matrix** (`docs/tools-authz.md`)
- viewer: none
- moderator: web_search, calculator
- admin / superadmin: all

**Prompt versioning**
- Prompts in `app/agent/prompts/` as `.j2` templates with `version` header comment
- Loaded via `PromptLoader.load(name, version)` — feature flag `prompt.<name>.version`

**Memory** — mem0 backed
- Schema version pinned in mem0 config
- `memory_migrations/` folder for schema bumps
- Per-user memory wipe endpoint (right-to-delete)

**PII** — Presidio
- VN patterns added: CCCD (12-digit), phone +84, bank account
- Mode `redact` default. Per-channel override via flag `guardrails.pii.mode.<channel>`
- Audit: detect counts logged to `pii_events(user_id, type, count, ts)`

**Conversation TTL**
- `conversations.last_message_at` index
- Daily Celery job: anonymize conversations older than 30d (drop user_id, hash content)

**Reset semantics**
| Channel | /reset behavior |
|---|---|
| Web | Close active conversation, start new |
| Slack DM | Same |
| Telegram | Same + ack message |

**Exit:** chaos test (LLM down → fallback, tool timeout → graceful, retrieval miss → "I don't know"); golden run green.

---

### E.4 M4 Eval gate

**Datasets** (`evals/golden/*.yaml`) — versioned, hashed in CI artifact
- `faq.yaml`, `rag.yaml`, `tools.yaml`, `guardrails.yaml`, `multilang.yaml`

**Per-metric thresholds** (`evals/thresholds.yaml`)
- RAG recall@5: -5% blocks
- Guardrails refusal precision: -3% blocks (strict)
- FAQ accuracy: -5% blocks
- Tool selection accuracy: -5% blocks
- Latency p95: +20% warns

**Drift detection**
- Weekly job: sample 100 prod queries, embed, compare distribution to golden via centroid distance
- Alert if drift > threshold → trigger eval set refresh ticket

**Cost ceiling per CI eval**: max $1 per run. Eval uses Gemini Flash only.

**Exit:** PR blocked when any threshold breached; admin can override with `eval-override` label + reason in PR description (audit logged).

---

### E.5 M5 Channels + feature flags

**Slack** (`app/channels/slack.py`)
- Bolt SDK socket mode (dev) / events API (prod)
- Verify signing secret on every event (timestamp window 5min)
- Idempotency: `slack_events.event_id` UNIQUE
- Reply queue: Celery `replies` queue, retry 3x exp backoff, dead-letter to `replies_dlq`

**Telegram** (`app/channels/telegram.py:115`)
- Webhook with secret token (header `X-Telegram-Bot-Api-Secret-Token`)
- HTTPS via Caddy
- Idempotency: `(chat_id, message_id)` UNIQUE
- `/reset` → close conversation row (fix existing TODO)

**Per-channel kill-switch**
- Flag `channel.<name>.enabled` → middleware returns 503 to webhook if off

**Feature flags table** — already specced in PLAN.md
- Migration: `0006_feature_flags.py`
- Seed flags: `chat.maintenance_mode=false`, `llm.model.primary=gemini-2.0-flash`, `rag.enabled=true`, `guardrails.pii.mode=redact`

**Exit:** pilot users chat from Web, Slack, Telegram against same backend. Kill-switch flips verified.

---

### E.6 M6 Admin + analytics + RBAC

**RBAC** (`app/core/security.py`)
- `users.role` enum: `viewer | moderator | admin | superadmin`
- FastAPI dependency `require_role(min_role)` on every admin endpoint
- Audit log table: `admin_audit(actor_id, action, resource_type, resource_id, before JSONB, after JSONB, ts)`

**Metabase**
- Container in `docker-compose.yml` (separate from prod), read-only DB role `metabase_ro`
- SSO via Caddy basic auth in front (pilot); proper SSO post-pilot
- Analytics views from `0005_analytics_views.py`

**Feedback workflow**
- Thumb-down → `feedback(id, message_id, user_id, rating, comment)` → review queue
- Moderator endpoint: `GET /api/admin/feedback/queue`, `POST /api/admin/feedback/{id}/resolve`

**Email deliverability**
- SPF, DKIM, DMARC on sending domain
- Bounce webhooks: Postmark + Resend → `email_bounces` table; auto-disable bouncing addresses
- Daily report content: DAU, msg count, avg latency, p95 latency, token spend, top intents, error rate, low-rating messages count

**Exit:** ops dashboard usable; admin ban + audit log verified; daily email sent.

---

### E.7 M7 Production deploy

**Target:** Single VPS (Hetzner / DigitalOcean / Vultr), 4vCPU 8GB, Ubuntu 24.04 LTS.

**Pipeline** (`.github/workflows/deploy.yml`)
- Trigger: tag `v*.*.*` push to main
- Steps: build image → Trivy scan (fail on HIGH/CRITICAL) → push to GHCR → SSH deploy → migration → smoke → on fail: rollback to previous tag

**Image registry:** GHCR (free, integrated). Retain last 10 tags.

**Migration policy:**
- Expand-contract for breaking schema (add col → backfill → switch reads → drop old)
- Migrations run pre-deploy step; rollback = re-deploy previous tag (no down-migrations in prod)

**Zero-downtime:**
- Caddy in front, 2 app replicas behind, rolling restart via compose `--no-deps`
- Long requests bounded by 60s graceful shutdown timer

**Backup:**
- Cron container runs `pg_dump | age -r <recipient> | aws s3 cp`
- Daily 02:00 VN. Lifecycle: 90d in S3, then Glacier 1y
- Restore drill: quarterly, restore to staging, run smoke

**TLS:** Caddyfile auto-acquire Let's Encrypt for subdomain.

**Resource sizing** (pilot < 50 user):
- postgres: 1 vCPU, 2GB
- redis: 0.5 vCPU, 512MB
- qdrant: 1 vCPU, 1GB
- app: 1 vCPU, 1.5GB (2 replicas → 3GB total)
- caddy: 0.2 vCPU, 128MB
- langfuse + clickhouse: 1 vCPU, 2GB

**Exit:** prod live, backup proven by restore drill.

---

### E.8 M8 Observability

**SLO:** p95 chat latency < 5s, availability 99% (error budget ~7h/month).

**Traces (OTel + Langfuse)**
- Spans: HTTP route, DB query, Redis call, LLM call (input/output captured to Langfuse), embedding, vector search, tool invocation
- Sampling: 100% in pilot (low volume); revisit at 10k+ msg/day

**Logs**
- structlog JSON → stdout → docker log driver → Loki (post-pilot) or simple `journald` for now
- Retention 30d; sensitive fields redacted (prompts hashed)

**Dashboards (Langfuse + Metabase)**
- Token spend per day per model
- p50/p95 latency per route
- Error rate per route
- Cache hit rate per layer
- Feedback rating distribution

**Alerts** (alertmanager or simple cron + email)
- Error rate > 5% over 10min
- p95 > 8s over 10min
- Daily spend > $2 (80% of $50/30 daily budget)
- Backup job failed
- Pre-commit / CI broken on main > 1h

**On-call:** 1 dev (founder). Runbook links from every alert.

**Synthetic monitoring:** UptimeRobot or BetterStack free tier → `/health` every 5min.

**Exit:** trace any user message ID → all spans; SLO dashboard live.

---

## Part F — Cross-cutting deliverables

### F.1 Threat model v0 (`docs/security/threat-model.md`)
STRIDE per component. Build before M0 hardening.

### F.2 Privacy + ToS (`docs/legal/privacy.md`, `tos.md`)
- Discloses LLM US transfer, retention, right-to-delete
- Linked from Chainlit footer + Slack /about + Telegram /help

### F.3 DPA review checklist
- OpenAI: data processing agreement signed + retention opt-out (zero-retention API)
- Google Gemini: Workspace / Cloud DPA
- Postmark + Resend: DPA on file

### F.4 Cost engineering
- Per-user daily token cap: 20k tokens (feature flag `quota.user.daily_tokens`)
- Per-route model tier (FAQ → Flash, agent → Pro)
- Cache hit target: > 30% (semantic + exact combined) by M6
- Daily spend alert at 80% of daily budget ($1.30/day)

### F.5 Incident response (`docs/runbooks/incident.md`)
- Severity levels (SEV1 outage, SEV2 degraded, SEV3 minor)
- On-call playbook: detect → page → mitigate → postmortem template
- Postmortem in `docs/postmortems/` with 5-whys

### F.6 ADR (`docs/adr/`)
- Start logging architectural decisions
- ADR-0001: deployment target (this plan)
- ADR-0002: LLM provider primary + fallback
- ADR-0003: secret store
- ADR-0004: tenancy model

---

## Part G — Pre-M0 deliverables (start here)

Before touching code:

1. Create `docs/corpus.md` — list every doc source intended for RAG, owner, format, sensitivity
2. Create `docs/security/threat-model.md` v0 — STRIDE pass per component
3. Create `docs/adr/0001-deployment.md` capturing Part D decisions
4. Author 3 ADRs above (LLM, secret, tenancy)
5. Draft privacy policy + ToS skeleton
6. Confirm domain + DNS access (subdomain for prod, separate for staging)
7. Provision VPS + S3/B2 bucket (prod target ready before M7)
8. Generate age keypair for SOPS; commit `.sops.yaml`
9. Pick allowlist of pilot user emails

Then M0 starts.

---

## Part H — Test + CI strategy (locked)

### H.1 Test layers + markers

| Layer | Marker | Scope | Where it runs |
|---|---|---|---|
| Unit | (none) | Pure logic, no I/O. Mocks for all externals. | Every push (parallel via `pytest-xdist`) |
| Integration | `integration` | Real Postgres + Redis + Qdrant via GH `services:` / testcontainers. Mocked LLM via `respx`. | Every push |
| E2E | `e2e` | Full FastAPI app via ASGI transport. All services real. LLM still mocked. | Every push |
| Eval (golden) | `eval` | LLM quality on golden YAMLs. Real LLM calls. Costs money. | Nightly cron + PR label `run-eval` |
| Load | (manual) | k6 RPS + soak | Pre-release manual |
| Chaos | (manual) | Failure injection drills | Pre-release manual |

`pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = [
  "integration: needs DB/Redis/Qdrant",
  "e2e: full app boot",
  "slow: > 5s",
  "eval: LLM quality, costs money",
]
addopts = "-ra --strict-markers --strict-config"
```

### H.2 CI workflow (`.github/workflows/ci.yml`)

Jobs (parallel where possible):

- **lint** — ruff check + ruff format --check + mypy --strict app/
- **unit** — `pytest -m "not integration and not e2e and not eval" -n auto`
- **integration** — Postgres + Redis as GH services, Qdrant via testcontainers; `pytest -m integration`
- **e2e** — same services + Qdrant; `pytest -m e2e`
- **security** — trivy fs (HIGH+/CRITICAL fail), pip-audit, detect-secrets scan
- **coverage** — aggregate from unit + integration + e2e; upload Codecov; diff-cover gate

Required for merge to main: lint, unit, integration, e2e, security, coverage (diff threshold).

Separate workflow `eval.yml`:
- Trigger: `schedule: cron '0 17 * * *'` (00:00 VN) + `workflow_dispatch` + PR label `run-eval`
- Budget: $1/run (Gemini Flash only)
- Output: per-metric scores compared to baseline → fail if threshold breached

### H.3 Coverage targets

- Overall: **80% line, 70% branch** on `app/`
- Per-module floor (in `.coveragerc`):
  - `app/core/`, `app/guardrails/`, `app/memory/pii.py` → **90%**
  - `app/services/` → **85%**
  - `app/api/`, `app/agent/` → **75%**
  - `app/channels/`, `app/workers/` → **70%**
- Exclude: `app/main.py`, `alembic/versions/`, `__init__.py`, generated code
- Diff-coverage on PR: new code ≥ **85%**, else warn (block at M4)
- Upload: Codecov (private repo paid; if cost issue → self-host Codecov-CE or use GH artifact)

### H.4 Fixture strategy (`tests/conftest.py`)

- Session-scoped: app instance, async engine
- Function-scoped: DB transaction + savepoint rollback per test (no truncate, no flake)
- Faker for synthetic users, conversations, documents
- `respx` to mock outbound HTTP (Gemini, OpenAI, Tavily, Postmark, Resend, Slack, Telegram)
- LLM mocks: recorded fixtures in `tests/fixtures/llm/*.json` — playback via custom `MockLLMGateway`
- No real LLM calls outside `eval` marker

### H.5 Services in CI

GH Actions `services:` for Postgres 16, Redis 7. Health-check gated.

Qdrant: testcontainers-python (no official GH service image). Spin-up cost ~5s; worth it for true integration.

Langfuse + Caddy: NOT in CI (mocked via respx). E2E only checks app boundary.

### H.6 Mocking LLM in tests

- Default: `respx` intercepts Gemini + OpenAI HTTP calls
- Recorded responses in `tests/fixtures/llm/`
- Tests assert prompt structure (count messages, role order, system prompt presence) — not exact text
- Update fixtures via `RECORD_LLM=1 pytest tests/...` (recorder mode hits real API once, writes fixture)
- Fixtures committed; reviewer checks diff for sanity

### H.7 Decisions (locked)

| # | Decision | Chosen |
|---|----------|--------|
| 34 | Coverage target | 80% line / 70% branch + per-module floors |
| 35 | Diff-cover threshold | 85% (warn pre-M4, block at M4) |
| 36 | Codecov | Codecov SaaS (free tier first; switch to self-host if private cost) |
| 37 | Eval cadence | Nightly cron + PR label + workflow_dispatch |
| 38 | Qdrant in CI | testcontainers-python |
| 39 | LLM mocking | respx + recorded fixtures + record mode env var |
| 40 | Test parallelism | pytest-xdist `-n auto` for unit only (integration/e2e serial to avoid DB races) |
| 41 | Eval cost cap per CI run | $1 USD (Gemini Flash) |

### H.8 Pilot test inventory (existing tests/ — needs alignment)

Existing files (untouched yet):
- `test_smoke.py` → expand to cover startup + 3 service pings (E.0)
- `test_analytics.py`, `test_channels.py`, `test_eval.py`, `test_guardrails.py`, `test_i18n.py`, `test_memory.py`, `test_quota.py`, `test_rag.py`, `test_tools_cache.py`, `test_ui.py`

M0 task: audit each file, classify with marker (unit / integration / e2e), fix broken imports, get suite green or skip-with-reason.

### H.9 Rollout

- M0: lint + unit + smoke (integration optional). Coverage upload + threshold warn-only.
- M1: integration + e2e green. Coverage threshold enforced at 70%.
- M2: bump coverage threshold to 75%.
- M3: bump to 80%. Diff-cover warn.
- M4: eval workflow blocks PR per Part E.4. Diff-cover blocks.
- M7+: load + chaos drills on staging before tag release.

---

## Part I — Errata (post-review 2026-05-16)

Advisor review surfaced 4 blocking contradictions + 6 non-blocking gaps. Resolutions applied below; original decision rows kept above for audit trail.

### I.1 Blocking fixes (user-resolved)

**I.1.1 gcal tool ↔ magic-link auth mismatch** (Decision #11 vs #17)
- Original #17: `gcal (read/create event)` implied per-user OAuth → conflicts with #11 (magic-link only, no Google OAuth).
- **Resolved:** `gcal_event` uses **service account** with **one shared calendar** (read + write). No per-user OAuth path.
- Impact on E.3: drop `OAuth scope calendar.events` line; replace with "service account JSON in SOPS-encrypted `secrets/prod.enc.yaml`; calendar id `chatbot-shared@…` set via env."
- Tool authz unchanged (viewer/moderator/admin matrix still applies — service account is the executor, RBAC gates *who can ask*).

**I.1.2 Eval gate cadence** (Decision #12 vs H.2)
- Original #12: "Block PR when any metric drops > 5%"; H.2: nightly + label-only. Inconsistent.
- **Resolved:** **Eval runs on every PR.** Within $50/mo budget (~$20/mo est at $1/run × ~20 PR/mo).
- Update H.2 trigger: `pull_request` (not `schedule`). Keep `workflow_dispatch` for manual reruns. Drop `run-eval` label gating.
- Keep $1 cost cap per run (Decision #41). Cron-nightly removed.
- Override mechanism unchanged: `eval-override` PR label + reason (audit logged).

**I.1.3 VPS sizing reality check** (Decision #9 vs E.7)
- Original #9 says 2vCPU/4GB; E.7 resource table sums to ~4.7 vCPU / 9.6 GB. Over budget.
- **Resolved:** **Keep VPS 2vCPU/4GB.** Switch Decision #20 telemetry from **Langfuse self-host → Langfuse cloud free tier**.
- E.7 resource table revised (remove langfuse + clickhouse rows):
  - postgres: 0.75 vCPU, 1.5 GB
  - redis: 0.25 vCPU, 256 MB
  - qdrant: 0.5 vCPU, 1 GB
  - app: 0.5 vCPU × 2 replicas = 1 vCPU, 1 GB total
  - caddy: 0.1 vCPU, 64 MB
  - **Sum: ~2.1 vCPU, ~3.8 GB** — fits 2vCPU/4GB with overcommit OK on pilot load.
- Langfuse cloud free tier limits (50k obs/mo) sufficient for < 500 msg/day.
- DPA: add Langfuse to F.3 DPA checklist (EU-hosted, GDPR-compliant per their docs — verify before sending data).

**I.1.4 Right-to-delete vs 90d backup** (Decision #14, #15, F.2)
- Original: live data anonymized 30d but backups retained 90d → user delete request can't reach backup tape.
- **Resolved:** **Live-only delete.** Backups expire on natural 90d cycle. Disclose explicitly in privacy.md.
- F.2 privacy.md MUST include clause: "Deletion requests apply to live production data and search indexes. Encrypted backups expire on a 90-day rolling cycle and are not selectively edited; deleted data persists in cold backups until that cycle completes, after which it is unrecoverable."
- No restore-then-redact procedure (cost+risk > benefit at pilot scale).

### I.2 Non-blocking gaps (errata)

**I.2.1 Qdrant snapshot in backup plan** — Decision #15 amendment.
- Add: Qdrant snapshot daily via `POST /collections/{name}/snapshots` → S3 alongside Postgres dump. Same 90d retention, same age-encryption.
- Restore drill (quarterly) covers both PG dump + Qdrant snapshot.

**I.2.2 mypy strict scope** — E.0 pre-commit.
- M0 scope: `app/core/` + `app/services/` strict only. Other modules: mypy non-strict (basic check).
- Expand strict per milestone: M2 adds `app/rag/`; M3 adds `app/agent/` + `app/memory/`; M5 adds `app/channels/`; M6 adds `app/api/`. Track in `pyproject.toml` `[tool.mypy.overrides]`.

**I.2.3 CI secrets policy** — new section in Part H.
- GH Actions encrypted repo secrets:
  - `GEMINI_API_KEY` (eval workflow only, scoped via environment `eval`)
  - `OPENAI_API_KEY` (eval workflow only, env `eval`)
  - `DEPLOY_SSH_KEY` (deploy workflow only, env `prod`)
  - `GHCR_PAT` (deploy workflow only)
  - `SOPS_AGE_KEY` (deploy workflow, for decrypting `prod.enc.yaml` server-side)
- Environment protection rules: `eval` env requires no approval; `prod` env requires manual approve from `huyntq`.
- Rotate quarterly per Decision #2 secret-rotation cadence. Runbook: `docs/runbooks/secrets.md`.
- Never echo secrets in logs; CI step `if: failure()` must not dump env.

**I.2.4 Embedding dim verification** — E.2 task before M2.
- Verify `app/rag/embedder.py` + Alembic `0002_rag_fields.py` use **768** (text-embedding-004), not 1536 (OpenAI ada-002 default).
- If mismatch: schema migration before any ingest. Add `embedding_dim` column to `document_chunks` for future migration tracking.
- Audit task: M0 exit checklist.

**I.2.5 Budget hard-cap enforcement** — F.4 spec.
- Daily cron job `app/workers/budget_guard.py`:
  - Query `SELECT SUM(cost_usd) FROM usage_events WHERE ts >= date_trunc('month', now())`.
  - If month-to-date > $40 (80% of $50 cap): set feature flag `llm.model.primary = gemini-2.0-flash` (downgrade); page admin via email + Slack.
  - If month-to-date > $50: set flag `chat.maintenance_mode = true`; page admin SEV1.
- Flag flips logged to `admin_audit` with actor = `system:budget_guard`.
- Reset on month rollover (cron re-evaluates against next month).

**I.2.6 Email enumeration leak** — E.1 magic-link spec.
- `POST /auth/request` MUST return identical `200 OK {"sent": true}` regardless of:
  - Email exists in allowlist or not.
  - Email is on bounce-suppression list or not.
  - Rate limit triggered (return 200 but skip send; log internally).
- Only send actual email if allowlisted + not suppressed + within rate.
- Token verify endpoint `POST /auth/verify` returns generic "invalid or expired" on any failure (no distinction).

### I.3 Updated decision deltas (supersede where conflicting)

| # | Field | Old | New |
|---|-------|-----|-----|
| 12 | Eval gate cadence | Block PR + nightly | **Run on every PR (within budget)** |
| 17 | gcal auth | OAuth scope | **Service account, single shared calendar** |
| 20 | Telemetry hosting | Langfuse self-host | **Langfuse cloud free tier** |
| 14 | Retention vs delete | (unspecified) | **Live-only delete; backups expire 90d natural cycle; disclosed in privacy.md** |
| 15 | Backup scope | Postgres only | **Postgres + Qdrant snapshot, daily, 90d** |

Errata ratified. Proceed to Part G pre-M0 deliverables.
