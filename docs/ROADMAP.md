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

---

## Phase breakdown (fine-grained)

Each sub-phase = 1 deliverable, 0.25–1 day, measurable exit. Total ≈ 45–55 dev-days (P0–P8) + ongoing P9.

### P0 — Foundation (M0+M1)

| # | Phase | Deliverable | Exit | Days |
|---|---|---|---|---|
| P0.1 | Env pin | `.python-version`, Docker base match, `requirements.lock` | `pip-sync` reproducible | 0.5 |
| P0.2 | Pre-commit | ruff/mypy/detect-secrets hooks | `pre-commit run -a` green | 0.5 |
| P0.3 | Compose up | Postgres + Redis + Qdrant healthchecks | `make up` → all healthy | 0.5 |
| P0.4 | Alembic init | head matches models, `alembic check` green | migration up/down clean | 0.5 |
| P0.5 | Smoke test | DB+Redis+Qdrant ping, lifespan boot | `pytest tests/test_smoke.py` green | 0.5 |
| P0.6 | CI lint+test | GH Action: ruff + pytest on PR | PR fails if lint/test red | 0.5 |
| P0.7 | LLM gateway | OpenAI/Anthropic adapter, 1 provider live | `POST /api/chat` non-stream response | 1 |
| P0.8 | Streaming | SSE + keepalive + disconnect handling | client cut → server cleanup | 1 |
| P0.9 | Google OAuth | login + session, state/nonce CSRF | browser login → chat | 1 |
| P0.10 | Logging + Sentry | JSON logs, redaction, Sentry init | logs leak no prompt, error → Sentry | 0.5 |
| P0.11 | Token accounting | `usage_events` row per message | row count = message count | 0.5 |
| P0.12 | Rate limit | `/api/chat` pre-auth + per-user | 429 triggers at threshold | 0.5 |
| P0.13 | LLM error taxonomy | rate-limit/context/filter/timeout map | each → distinct HTTP + log tag | 0.5 |

### P1 — MVP RAG (M2)

| # | Phase | Deliverable | Exit | Days |
|---|---|---|---|---|
| P1.1 | Corpus inventory | source list YAML, owner, license | doc committed | 0.5 |
| P1.2 | Chunker | size+overlap+semantic boundary | unit test on 5 doc types | 1 |
| P1.3 | Embedding lock | model name+dim pinned, migration plan | config validates dim match | 0.5 |
| P1.4 | Ingestion worker | parse→chunk→embed→Qdrant | 100 docs ingest under SLA | 1 |
| P1.5 | Dedup | content hash + cosine near-dup | re-ingest → 0 duplicate | 0.5 |
| P1.6 | Retrieval | top-k + tenant filter | recall@5 ≥ 0.85 golden | 1 |
| P1.7 | Reranker | tune threshold | nDCG ≥ target | 1 |
| P1.8 | Citation render | source title+page+chunk_id chip | Chainlit click → source | 0.5 |
| P1.9 | Re-index runbook | full vs incremental script | dry-run pass | 0.5 |

### P2 — Agent + Memory (M3)

| # | Phase | Deliverable | Exit | Days |
|---|---|---|---|---|
| P2.1 | Tool registry | name/schema/timeout/retry spec | 3 tools registered | 0.5 |
| P2.2 | Tool authz | role × tool matrix | unauthorized → 403 | 0.5 |
| P2.3 | Agent graph | route + fallback + retry-backoff | chaos input → graceful | 1 |
| P2.4 | Memory store | mem0 wire, schema v1 | recall across session | 1 |
| P2.5 | PII detect | VN ID/phone regex + ML | golden PII set ≥ 95% | 1 |
| P2.6 | PII policy | off/detect/redact/block per channel | flag-driven behavior | 0.5 |
| P2.7 | Guardrails | OpenAI moderation + VN patterns | `test_guardrails.py` green | 1 |
| P2.8 | Reputation | `moderation_events` query | repeat offender → block | 0.5 |
| P2.9 | Conversation TTL | archive job | old conv archived | 0.5 |
| P2.10 | /reset semantics | per-channel behavior table | matrix test pass | 0.5 |

### P3 — Eval Gate (M4)

| # | Phase | Deliverable | Exit | Days |
|---|---|---|---|---|
| P3.1 | Golden YAML | 5 sets (faq/tools/rag/guardrails/multilang) | dataset versioned + hashed | 1 |
| P3.2 | Eval CLI | `python -m app.eval.cli` runs all | scores persisted | 0.5 |
| P3.3 | Baseline | snapshot scores → DB | baseline row exists | 0.25 |
| P3.4 | Regression gate | CI fail if drop > threshold | PR blocked on synthetic regression | 0.5 |
| P3.5 | Per-metric threshold | not single X% | YAML config drives gate | 0.25 |
| P3.6 | Cost ceiling | budget per eval run | over-budget → abort | 0.5 |
| P3.7 | Drift detect | prod prompt dist vs golden | alert on KL divergence | 1 |

### P4 — Channels + Feature flags (M5)

| # | Phase | Deliverable | Exit | Days |
|---|---|---|---|---|
| P4.1 | Feature flags core | `FlagService` + Redis + 1 flag | `chat.maintenance_mode` works | 1 |
| P4.2 | Flag admin API | CRUD + audit | curl create→eval→audit | 1 |
| P4.3 | Flag rules + % rollout | targeting + bucket | chi-square pass | 1 |
| P4.4 | Telegram webhook | secret token verify | unsigned → 401 | 0.5 |
| P4.5 | Telegram dedup | idempotency key DB unique | replay → no dup | 0.5 |
| P4.6 | Slack signing | HMAC verify middleware | bad sig → 401 | 0.5 |
| P4.7 | Slack threading | thread_ts ↔ conv_id map | reply lands in thread | 0.5 |
| P4.8 | Outbound queue | retry + DLQ | provider 5xx → retry → DLQ | 1 |
| P4.9 | Upload allowlist | MIME + size per channel | reject .exe, > limit | 0.5 |
| P4.10 | Per-channel flag wire | RAG off Telegram via flag | flag toggle → behavior change | 0.25 |

### P5 — Admin + Analytics (M6)

| # | Phase | Deliverable | Exit | Days |
|---|---|---|---|---|
| P5.1 | Metabase auth | SSO/shared secret, read-only role | login works, no write | 0.5 |
| P5.2 | Admin RBAC | viewer/moderator/superadmin | unauthorized → 403 | 0.5 |
| P5.3 | Admin audit | every action logged | audit row per mutation | 0.5 |
| P5.4 | Feedback queue | thumb-down → review → resolved | state machine works | 1 |
| P5.5 | Email pipeline | SPF/DKIM/DMARC + bounce | inbox placement test | 1 |
| P5.6 | Daily report | metrics spec + cron | email lands 8am | 0.5 |
| P5.7 | Dashboards | flag state, exposure, cost, latency | Metabase panel exists | 1 |

### P6 — Pre-Prod (M7 prep)

| # | Phase | Deliverable | Exit | Days |
|---|---|---|---|---|
| P6.1 | Deploy target decision | doc + ADR | Decision #1 filled | 0.5 |
| P6.2 | Secret store decision | SOPS/Vault/KMS | Decision #2 filled, secrets migrated | 1 |
| P6.3 | Multi-tenant schema | tenant_id everywhere | migration applied | 1 |
| P6.4 | Threat model v0 | STRIDE per component | doc + review | 1 |
| P6.5 | Backup target | encryption + retention | restore drill pass | 1 |
| P6.6 | DNS + TLS | LE automation | cert renew auto | 0.5 |

### P7 — Production Deploy (M7)

| # | Phase | Deliverable | Exit | Days |
|---|---|---|---|---|
| P7.1 | Image build + scan | Trivy in CI | block on HIGH CVE | 0.5 |
| P7.2 | Registry + retention | push tagged images | old tags GC'd | 0.5 |
| P7.3 | Migration policy | expand-contract docs | breaking change drill | 0.5 |
| P7.4 | Zero-downtime deploy | blue-green or rolling | deploy mid-traffic, 0 5xx | 1 |
| P7.5 | Smoke + rollback gate | post-deploy probe | bad deploy auto-rollback | 1 |
| P7.6 | Resource sizing | CPU/RAM per service | load test → sizing | 1 |
| P7.7 | Autoscale rules | HPA or equiv | spike → scale → recover | 1 |
| P7.8 | SBOM | per release | artifact attached | 0.25 |

### P8 — Observability (M8)

| # | Phase | Deliverable | Exit | Days |
|---|---|---|---|---|
| P8.1 | SLO numbers | p95, availability, error budget | docs + dashboard | 0.5 |
| P8.2 | Log retention | tier + lifecycle | old logs → cold storage | 0.5 |
| P8.3 | Trace sampling | rate config | cost vs coverage tuned | 0.5 |
| P8.4 | PII scrub traces | sanitizer in pipeline | grep test → no PII | 0.5 |
| P8.5 | Alert routing | on-call rotation | page test fires | 0.5 |
| P8.6 | Runbook links | alert → runbook URL | every alert has runbook | 0.5 |
| P8.7 | Synthetic probe | external health check | down detect < 1min | 0.5 |

### P9 — Hardening (cross-cutting, ongoing)

| # | Phase | Deliverable |
|---|---|---|
| P9.1 | Cost cap | per-user token budget + alert |
| P9.2 | Semantic cache | hit-rate target |
| P9.3 | Circuit breaker | every external call |
| P9.4 | DR drill | RPO/RTO measured |
| P9.5 | Chaos drill | kill-pod, fill-disk, LLM-down |
| P9.6 | Load test | k6 plan, soak |
| P9.7 | Pen-test | scope + cadence |
| P9.8 | DPA review | OpenAI/Anthropic/Google |
| P9.9 | VN PDPD checklist | compliance gap closed |
| P9.10 | Incident response | runbook + drill |

### Phase → Release stage mapping

| Stage | Phases | Demo target |
|---|---|---|
| Foundation | P0 | Dev stack boot, chat E2E real LLM |
| MVP internal | P1 + P2 | RAG + agent + guardrail, internal demo |
| Pilot | P3 + P4 | Eval gate, 1–2 channel live, 10–50 real users |
| GA | P5 + P6 + P7 | Admin/analytics, prod deploy, multi-tenant |
| Scale | P8 + P9 | SLO sustained 30d, cost within budget |
