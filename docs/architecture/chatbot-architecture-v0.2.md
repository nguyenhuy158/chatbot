# AI Chatbot — Architecture Document v0.2

**Author:** Huy
**Version:** 0.2 (Full scope)
**Date:** 2026-05-14
**Status:** Pre-implementation review

---

## 0. Changelog

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-05-14 | Initial draft, core architecture |
| 0.2 | 2026-05-14 | Added 28 detailed topics, Odoo deferred, multi-tenant ready, caching simplified |

---

## 1. Mục tiêu & Scope

### 1.1 Mục tiêu

AI chatbot **đa năng** phục vụ cả external customer + internal staff, với 3 modes:

| Mode | Mô tả | Audience |
|---|---|---|
| Customer Support | FAQ, hỏi đáp sản phẩm | Khách external |
| Internal Tool | Tra cứu policy, SOP, data công ty | Staff |
| RAG Q&A | Hỏi đáp trên kho tài liệu | Cả hai (phân quyền) |

### 1.2 Scope MVP (locked)

| Có | Không (defer) |
|---|---|
| Multi-lang VN/EN auto-detect | Voice / audio |
| Memory dài hạn theo user | Fine-tuning |
| Tools: web search, custom APIs | **Odoo integration** (defer M2) |
| Web (Chainlit) + Slack + Telegram | Zalo |
| Image input (Gemini Flash) | Video |
| SSO Google/Microsoft | Native mobile app |
| Tenant-ready schema | Full multi-tenant runtime |

### 1.3 Success metrics

| Metric | Target W4 | Target M3 |
|---|---|---|
| Response latency p95 | <5s | <3s |
| Answer correctness (RAGAS) | >70% | >85% |
| User retention (DAU/MAU) | >20% | >40% |
| Cost per query | <$0.005 | <$0.003 |
| Hallucination rate | <15% | <5% |
| Eval suite pass rate | >70% | >85% |

---

## 2. High-level Architecture

```
┌────────────────────────────────────────────────────────────┐
│                       CHANNELS                              │
│  Web (Chainlit, responsive)  │  Slack Bot  │  Telegram Bot │
└────────────────────────┬───────────────────────────────────┘
                         │ HTTPS / WSS
                         ▼
┌────────────────────────────────────────────────────────────┐
│              API GATEWAY (FastAPI + SSO)                    │
│  OAuth Google/MS │ Rate limit │ Quota check │ Cookie consent│
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│                  GUARDRAILS (Input)                         │
│  OpenAI Moderation │ VN regex │ Gemini classifier (borderline)│
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│                  CACHE CHECK (L1 exact)                     │
│         Redis: hash(query+ctx) → cached response            │
└────────────────────────┬───────────────────────────────────┘
                         │ miss
                         ▼
┌────────────────────────────────────────────────────────────┐
│                  ROUTER LAYER                               │
│  Role detect │ Intent classify │ ACL filter │ Persona inject │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│              LANGGRAPH AGENT (State Machine)                │
│                                                             │
│   load_memory → plan → [rag | tool] → generate → save_mem  │
│                                                             │
│   ┌──────┐   ┌──────┐   ┌─────┐   ┌──────────┐            │
│   │ mem0 │   │ LLM  │   │ RAG │   │ Tools    │            │
│   │      │   │ Gate │   │     │   │ Web/Custom│           │
│   └──────┘   └──────┘   └─────┘   └──────────┘            │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│                  GUARDRAILS (Output)                        │
│  Moderation │ PII redact │ Citation inject │ Disclaimer     │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│                    DATA LAYER                               │
│  Postgres (pgvector, tenant_id) │ Redis │ Azure Blob       │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│        OBSERVABILITY (OpenTelemetry → SigNoz)               │
│        Logs │ Metrics │ Traces │ Langfuse (LLM)             │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│        ANALYTICS (Metabase on Postgres views)               │
│        DAU/MAU │ CSAT │ Top intents │ Cost per user         │
└────────────────────────────────────────────────────────────┘
```

---

## 3. Component Design

### 3.1 API Gateway (FastAPI)

| Concern | Detail |
|---|---|
| Framework | FastAPI 0.115+ |
| Auth | Authlib + JWT (15min access + 7d refresh) |
| SSO | Google Workspace + Microsoft Entra ID |
| Rate limit | 60 req/min/user, 10/min/IP |
| CORS | Whitelist frontend domains |
| Validation | Pydantic v2 |
| Cookie consent | Banner GDPR/PDPL compliant |
| AI disclosure | Banner: "Bạn đang chat với AI" |

**Endpoints:**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/chat` | Streaming chat (SSE) |
| GET | `/api/conversations` | List conversations |
| DELETE | `/api/conversations/{id}` | Delete conversation |
| POST | `/api/feedback` | Thumbs up/down + comment |
| POST | `/api/documents/upload` | Upload PDF/docx |
| POST | `/api/images/upload` | Upload image (multimodal) |
| GET | `/api/me/data` | GDPR export (ZIP) |
| DELETE | `/api/me/data` | GDPR delete |
| GET | `/api/me/settings` | User prefs (lang, memory) |
| GET | `/api/me/quota` | Current quota usage |
| GET | `/auth/login/{provider}` | OAuth flow |
| GET | `/auth/callback` | OAuth callback |
| GET | `/admin/*` | SQLAdmin panel (role-gated) |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus (internal) |

### 3.2 Router Layer

```python
# Pseudo-code
def route(request, user):
    role = user.role
    intent = classify_intent(request.message)  # Gemini Flash
    lang = detect_lang(request.message)

    if role == "external":
        allowed_collections = ["public_docs", "faq"]
        system_prompt = EXTERNAL_PROMPT
        allowed_tools = ["web_search"]
    else:
        allowed_collections = ["public_docs", "faq", "internal_sop"]
        system_prompt = INTERNAL_PROMPT
        allowed_tools = ["web_search", "custom_apis"]

    return AgentContext(
        tenant_id=user.tenant_id,
        intent=intent,
        lang=lang,
        rag_filter={
            "collection__in": allowed_collections,
            "tenant_id": user.tenant_id,
        },
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
    )
```

**Critical:** ACL filter trong pgvector `WHERE` clause, không post-filter.

### 3.3 LangGraph Agent

```
START → load_memory → plan ──┐
                              ├─→ rag_search ──┐
                              ├─→ tool_call ───┤
                              └─→ direct ──────┤
                                                ▼
                                            generate
                                                │
                                                ▼
                                            save_memory
                                                │
                                                ▼
                                              END
```

**State schema:**

```python
class AgentState(TypedDict):
    tenant_id: str
    user_id: str
    role: Literal["internal", "external"]
    lang: str
    messages: list[BaseMessage]
    memories: list[Memory]
    rag_results: list[Chunk]
    rag_citations: list[Citation]
    tool_results: list[ToolResult]
    final_answer: str
    metadata: dict  # tokens, cost, latency, model
```

**Context window management (#5):**

| Strategy | Detail |
|---|---|
| Sliding window | 10 messages gần nhất raw |
| Summary buffer | Tóm tắt cũ bằng Gemini Flash |
| Token budget | 4000 tokens history cap |
| Tool trim | Output >1000 tokens → summarize |
| Pinning | User pin message → không prune |

### 3.4 LLM Gateway

| Tier | Model | Use case | In/Out per M |
|---|---|---|---|
| Cheap | Gemini 2.5 Flash | Intent, classify, summary | $0.30 / $2.50 |
| Main | Claude Haiku 4.5 | Default chat | $1 / $5 |
| Hard | Claude Sonnet 4.6 | Complex reasoning, agent | $3 / $15 |

**Failover chain (#21):**

```
Primary (Gemini Flash) → Claude Haiku → Sonnet → OpenAI GPT → static FAQ
```

Circuit breaker với `tenacity`, 3 retries với exponential backoff.

### 3.5 Memory Layer (mem0)

| Type | TTL | Examples |
|---|---|---|
| factual | Forever | "User works at TechCoop" |
| preference | Forever | "Prefers concise answers" |
| context | 30d | "Working on Farmnet RFC" |
| episodic | 90d | "Asked about pgvector on 2026-05-10" |

**Privacy:**
- UI `/settings/memory` để view/edit/delete
- PII detection (Presidio) trước khi lưu
- Per-user isolation (tenant_id + user_id filter)

**Schema:**

```sql
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    user_id UUID NOT NULL,
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(768),
    metadata JSONB,
    pinned BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON memories (tenant_id, user_id, memory_type);
```

### 3.6 RAG Pipeline

**Ingestion:**

```
PDF/DOCX/Notion URL → Parser (unstructured) → Chunker (semantic 512+64) →
Embedder (Gemini text-embedding-001 768d) → pgvector + metadata
```

**Retrieval:**

```
Query → HyDE rewrite → Embed → pgvector ANN (top 20) →
Cross-encoder rerank → Top 5 → Context inject
```

**Citation (#7):**

| Element | Format |
|---|---|
| Inline | `[1]` after each factual claim |
| Source list | "Nguồn: 1. SOP.pdf (p.12), 2. ..." |
| Clickable | Link + chunk highlight |
| Confidence | 🟢 high / 🟡 med / 🔴 low |
| No source | "Không tìm thấy trong tài liệu, đây là general knowledge" |

**Schema:**

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    collection TEXT NOT NULL,
    title TEXT,
    source_url TEXT,
    owner_email TEXT,
    acl JSONB,
    expires_at TIMESTAMPTZ,
    status TEXT DEFAULT 'approved' CHECK (status IN ('draft','approved','archived')),
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding VECTOR(768),
    chunk_index INTEGER,
    metadata JSONB
);
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
```

**KB maintenance (#23):**

| Mechanism | Detail |
|---|---|
| Owner per doc | Alert >180d không update |
| Expiry date | Expired → flag "outdated" in response |
| Coverage gap | Weekly report top "no result" queries |
| Quality score | Citation count / view ratio |
| Approval workflow | draft → approved → archived |

### 3.7 Tools (Function Calling)

**MVP scope:**

| Tool | Allowed roles | Rate limit |
|---|---|---|
| `web_search` (Tavily) | external + internal | 10/day ext, 50/day int |
| `web_fetch` | both | 20/day ext, 100/day int |
| `get_current_time` | both | unlimited |
| `calculator` | both | unlimited |

**Deferred M2:**
- `odoo_query` (full Odoo integration)
- Custom business APIs

**Tool audit log** (#24 spirit):

```sql
CREATE TABLE tool_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    tool_name TEXT,
    input JSONB,
    output JSONB,  -- redacted if PII
    success BOOLEAN,
    error TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.8 Guardrails (3-layer #3, #17)

**Input filter:**

```
Layer 1: OpenAI Moderation API (free, EN strong)
Layer 2: VN bad words regex (custom list)
Layer 3: Gemini Flash classifier (borderline: jailbreak, prompt injection)
```

**Output filter:**
- Same moderation pass on response
- PII redaction (Presidio)
- Citation injection
- Disclaimer footer

**User behavior tracking:**

| Behavior | Response |
|---|---|
| Chửi bậy #1 | Warning |
| Chửi bậy #2 | Refuse + log |
| Chửi bậy #3 | Temp ban 24h |
| Spam >100/h | Auto rate limit + admin alert |
| Jailbreak | Refuse + ML score user |
| Reputation <30 | Permanent ban review |

### 3.9 Cache Strategy (#20)

**MVP: L1 + L4 only**

| Layer | What | TTL | Storage |
|---|---|---|---|
| L1 | Exact match `hash(query+ctx+role)` → response | 1h | Redis |
| L4 | LLM prompt cache (Anthropic/Gemini native) | Provider managed | — |

**Savings ước tính:** 15-25% (full L1+L2+L3+L4 = 30-40%).

### 3.10 Quota Enforcement (#18)

| Quota | External | Internal |
|---|---|---|
| Messages/day | 50 | 500 |
| Tokens/day | 50k | 500k |
| Cost/day cap | $0.50 | $5 |
| Web search/day | 10 | 50 |

**Implementation:**
- Redis counter `quota:{user_id}:{date}:{metric}`
- Reset 00:00 GMT+7
- 80% warning, 100% hard block
- Admin override via admin panel

---

## 4. Data Model

### 4.1 Tenant-ready schema (#19)

Mọi table có `tenant_id UUID NOT NULL DEFAULT '...'`. RLS chưa bật, sẵn sàng bật sau.

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    email TEXT NOT NULL,
    name TEXT,
    role TEXT NOT NULL CHECK (role IN ('internal', 'external', 'admin')),
    sso_provider TEXT,
    sso_subject TEXT,
    preferences JSONB DEFAULT '{}',  -- lang, mem opt-out, etc
    reputation_score INTEGER DEFAULT 100,
    banned_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ,
    UNIQUE (tenant_id, email)
);

-- Conversations
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    channel TEXT,  -- web | slack | telegram
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT CHECK (role IN ('user','assistant','tool','system')),
    content TEXT NOT NULL,
    tool_calls JSONB,
    citations JSONB,
    tokens_input INTEGER,
    tokens_output INTEGER,
    cost_usd NUMERIC(10,6),
    latency_ms INTEGER,
    model TEXT,
    cached BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON messages (conversation_id, created_at);

-- Feedback (#8)
CREATE TABLE feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    message_id UUID REFERENCES messages(id),
    user_id UUID REFERENCES users(id),
    rating SMALLINT CHECK (rating IN (-1, 1)),
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Moderation events
CREATE TABLE moderation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID,
    event_type TEXT,  -- profanity | jailbreak | spam | nsfw
    severity TEXT,  -- low | med | high
    content_snippet TEXT,
    action_taken TEXT,  -- warn | refuse | ban
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit log (immutable)
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    actor_id UUID,
    action TEXT,
    target_type TEXT,
    target_id UUID,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- No UPDATE/DELETE allowed (revoke at role level)
```

---

## 5. Security Model

### 5.1 Threat model (updated)

| Threat | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Prompt injection | High | Med | 3-layer guardrails, system prompt isolation |
| RAG ACL leak | High | High | pgvector WHERE filter, tenant_id NOT NULL |
| Memory contamination | Low | High | user_id + tenant_id FK |
| API key leak | Med | High | Azure Key Vault, env vars only |
| Cost DDoS | Med | Med | Per-user quota + cost cap |
| Tool exfiltration | Low | High | Tool allowlist per role, audit log |
| Cross-channel leak | Med | High | conversation_id per channel |
| Reputation gaming | Low | Low | Score read-only via service |

### 5.2 PII handling

- Detect: Presidio (English) + custom VN regex (CCCD, số điện thoại)
- Redact trước log + LLM call (configurable)
- User opt-out memory in `/settings`

---

## 6. Compliance (#16)

| Requirement | Implementation |
|---|---|
| Right to access | `GET /api/me/data` → ZIP |
| Right to delete | `DELETE /api/me/data` → hard + propagate |
| Right to portability | JSON/Markdown export |
| Consent tracking | Versioned T&C, `user_consents` table |
| Data residency | ⚠️ OPEN Q1 — legal confirm trước W2 |
| DPO contact | Footer email |
| Breach notification | 72h template trong runbook |
| Audit trail | `audit_log` table, append-only |
| Cookie consent | Banner GDPR/PDPL |
| AI disclosure | Banner "Bạn đang chat với AI" |
| Data Processing Agreement | Sign với Anthropic + Google |

**Vietnam PDPL (Nghị định 13/2023):**
- Notify Ủy ban Bảo vệ dữ liệu cho 1 số xử lý
- Customer data của VN citizen có thể cần lưu VN region

---

## 7. Localization (#22)

| Element | Implementation |
|---|---|
| Detect lang | `langdetect` library |
| Mixed input | Detect dominant, default VN cho VN user |
| User override | `/settings` → "luôn trả VN" |
| Number format | `babel` library (1.000.000 vs 1,000,000) |
| Date format | DD/MM/YYYY (VN) vs MMM DD (EN) |
| Currency | VND default, toggle |
| Bot system prompt | "Always respond in `{user_lang}`" |
| Code/term | Keep English, không dịch |
| UI i18n | Chainlit i18n + VN translation file |

---

## 8. Observability

### 8.1 Stack

| Layer | Tool |
|---|---|
| Instrumentation | OpenTelemetry Python SDK |
| LLM tracing | Langfuse (cost, prompt, response) |
| Backend | SigNoz (self-host) |
| Alerts | SigNoz Alertmanager → Slack |
| Business analytics | Metabase on Postgres views |

### 8.2 Key metrics

| Metric | Alert |
|---|---|
| `chat_requests_total` | — |
| `chat_latency_seconds` p95 | >8s |
| `llm_tokens_total{type}` | — |
| `llm_cost_usd_total` | >$10/day |
| `tool_call_errors_total` | >5%/5min |
| `rag_no_results_ratio` | >30% |
| `auth_failures_total` | >10/min |
| `quota_exhausted_total` | — |
| `moderation_events_total{type}` | jailbreak spike |
| `cache_hit_ratio` | <10% (cache useless) |

### 8.3 Business metrics (#27 - Metabase)

| Metric | SQL |
|---|---|
| DAU | `COUNT(DISTINCT user_id) WHERE last_active = today` |
| MAU | `COUNT(DISTINCT user_id) WHERE last_active >= today-30` |
| Stickiness | DAU/MAU |
| CSAT | `SUM(rating=1) / COUNT(*)` from feedback |
| Top intents | Cluster from `messages.metadata->>'intent'` |
| Cost/MAU | `SUM(cost_usd) / MAU` |
| Unanswered rate | `COUNT(no_rag_results) / COUNT(*)` |
| Churn | last 30d users not in last 7d |

---

## 9. Deployment & Channels

### 9.1 Infrastructure

| Component | Where |
|---|---|
| App (FastAPI) | Docker + Dokploy |
| Postgres + pgvector | Azure Postgres Flexible |
| Redis | Docker container |
| SigNoz | Self-host VPS (existing) |
| Metabase | Docker container |
| Langfuse | Docker self-host |
| Object storage | Azure Blob hoặc MinIO |

### 9.2 Channels (#28)

| Channel | Stack | Phase |
|---|---|---|
| Web | Chainlit (responsive) | W1 |
| Slack | bolt-python | W4 |
| Telegram | python-telegram-bot | W4 |
| Zalo | Defer M2+ | — |
| Native mobile | Defer M3+ | — |

**Mobile (#28 - responsive web + Telegram/Slack):**
- Viewport meta tag
- Touch targets 44x44px min
- Voice input via Web Speech API
- Power users dùng Telegram/Slack cho push noti

### 9.3 Streaming UX (#4)

| Feature | Detail |
|---|---|
| Token streaming | SSE qua FastAPI |
| Typing indicator | "AI đang suy nghĩ..." |
| Tool indicator | "🔍 Đang tìm web..." |
| Cancel | AbortController + LangGraph cancel |
| Partial save | Resume from cancelled message |

### 9.4 Onboarding (#13)

| Element | Detail |
|---|---|
| Welcome message | "Chào, tôi là bot X..." |
| Sample prompts | 4 buttons quick start |
| Capability tour | 3-slide modal lần đầu |
| Empty state | Example queries |
| Tooltip | Hover tools → explain |

---

## 10. Admin Panel (#14 - SQLAdmin)

| Feature | Priority |
|---|---|
| User management (list, ban, role) | High |
| Document management (upload, delete, reindex, approve) | High |
| Conversation viewer (search, filter, export) | Med |
| Cost dashboard per user/model | High |
| Feedback queue (review 👎) | High |
| Moderation events viewer | High |
| Quota override | High |
| Audit log viewer | High |
| Eval results | Med |
| Prompt editor + version | Med |

**Stack:** SQLAdmin on `/admin/*`, JWT role gate `admin` only.

---

## 11. Eval & Testing (#1)

| Element | Detail |
|---|---|
| Framework | RAGAS + DeepEval (open source) |
| Metrics | faithfulness, answer_relevance, context_precision, hallucination_rate |
| Golden set | 200 câu hỏi labeled internal/external, VN/EN mix |
| Smoke test | 10 câu, pre-commit hook |
| Full suite | Nightly CI, 200 câu |
| Regression | Block merge if score drop >5% |
| Tracking | Langfuse for prompt comparison |

**Test categories:**

| Category | Count |
|---|---|
| FAQ Q&A | 40 |
| RAG retrieval | 40 |
| Multi-turn context | 30 |
| Memory recall | 20 |
| Tool calling | 20 |
| Guardrails (should refuse) | 30 |
| Multi-lang VN/EN | 20 |

---

## 12. Prompt Engineering (#2)

| Element | Detail |
|---|---|
| Storage | Langfuse prompt management |
| Versioning | Semver `system_v1.2.3` |
| A/B test | 10% traffic new prompt |
| Template | Jinja2 |
| Variables | `{user_role}`, `{lang}`, `{rag_ctx}`, `{date}`, `{user_name}` |

---

## 13. Multi-turn Intent (#6)

| Approach | Detail |
|---|---|
| Coref | LLM handles with history |
| Intent stack | `current_topic` in state |
| Follow-up | Short msg + connector words → inherit context |
| Topic switch | Embedding sim with prev msg |

---

## 14. Batch Jobs (#9) + Webhooks (#10)

### 14.1 Batch (Celery beat)

| Job | Schedule |
|---|---|
| Re-index docs | Daily 2am |
| Stale content scan | Weekly |
| Cost report email | Daily 9am |
| Memory cleanup (TTL) | Daily |
| Eval suite | Nightly |
| Conversation archive (>90d) | Monthly |
| Backup pg_dump + pgslim | Hourly |

### 14.2 Webhooks (M2 defer for proactive)

MVP: receive webhook only. Proactive notification defer.

| Endpoint | Use |
|---|---|
| `POST /api/events/document-updated` | Trigger reindex |
| `POST /api/events/external` | Future Odoo events |

---

## 15. Multimodal (#11)

**MVP:** Image input only via Gemini Flash.

| Feature | Detail |
|---|---|
| Image upload | `/api/images/upload` → Blob → URL |
| Processing | Pass URL to Gemini Flash multimodal |
| Use cases | Screenshot error, OCR, photo of doc |
| Limit | 10MB, JPG/PNG/WebP, 5 images/day external |
| Defer M2 | Voice (Whisper), Video |

---

## 16. Latency Optimization (#25)

| Technique | Effort | Saving |
|---|---|---|
| Streaming first token | Low | UX 10x perceived |
| Parallel tool calls | Med | 2-3x multi-tool |
| Speculative RAG | Med | -500ms |
| HNSW tuning `ef_search=40` | Low | -100ms |
| pgbouncer pooling | Low | -50ms |
| Redis pipelining | Low | -30ms |
| Model routing (easy→Flash) | Med | -1s |
| asyncpg async everywhere | Low | -100ms |
| Edge deploy | High | Defer |

**Targets:**
- First token: <2s
- Full response: <5s p95
- Tool-heavy: <10s p95

---

## 17. Legal Disclaimers (#26)

| Where | Text |
|---|---|
| Footer every response | "AI có thể sai, vui lòng xác minh thông tin quan trọng" |
| Legal/medical/financial topics | "Không phải tư vấn chuyên nghiệp" |
| Signup | T&C + Privacy checkbox |
| Footer | Privacy Policy link, DPO email |
| Cookie banner | GDPR/PDPL |
| First-time | "Bạn đang chat với AI, không phải người" |
| Data usage | "Conversation lưu để improve, có thể anonymize" |
| Opt-out | `/settings` → no training |

---

## 18. Backup & DR (#15)

| Element | Detail |
|---|---|
| Tool | `pg_dump` + Huy's `pgslim` |
| Schedule | Hourly incremental, daily full, weekly archive |
| Storage | Azure Blob (hot/cool/archive tiers) |
| Retention | 7d daily + 4w weekly + 12m monthly |
| Encryption | At-rest (Azure) + in-transit |
| RPO | <1 hour |
| RTO | <4 hours |
| Restore drill | Monthly to staging |
| Runbook | `docs/runbooks/restore.md` |

---

## 19. Roadmap (Full Scope)

### Phase 1: Foundation (Week 1-2)

- [ ] Repo scaffolding (FastAPI + LangGraph + Alembic)
- [ ] Postgres schema + migrations (tenant_id ready)
- [ ] SSO Google + MS login
- [ ] LLM gateway (Gemini + Claude swap + failover)
- [ ] Basic chat endpoint with streaming SSE
- [ ] Chainlit web UI
- [ ] Cookie consent + AI disclosure banner
- [ ] Docker + Dokploy deploy
- [ ] OpenTelemetry basic instrumentation
- [ ] SigNoz dashboard

### Phase 2: RAG + Citation (Week 2-3)

- [ ] PDF/DOCX ingestion (unstructured)
- [ ] pgvector + HNSW index
- [ ] Gemini embedding pipeline
- [ ] HyDE rewrite + reranker
- [ ] Collection ACL filter
- [ ] Citation injection
- [ ] Upload UI
- [ ] Document approval workflow

### Phase 3: Memory + Agent (Week 3-4)

- [ ] mem0 integration
- [ ] LangGraph agent (plan/rag/tool/generate/save_mem)
- [ ] Memory management UI
- [ ] PII redaction (Presidio + VN regex)
- [ ] Context window mgmt (sliding + summary)
- [ ] Multi-turn intent tracking

### Phase 4: Guardrails + Quota (Week 4-5)

- [ ] OpenAI Moderation integration
- [ ] VN regex bad words
- [ ] Gemini Flash classifier (borderline)
- [ ] Quota enforcement (Redis counters)
- [ ] User reputation score
- [ ] Moderation events table + alerting

### Phase 5: Tools + Cache (Week 5)

- [ ] Tool framework
- [ ] Web search (Tavily)
- [ ] Web fetch
- [ ] Time + calculator
- [ ] Tool audit log
- [ ] L1 exact cache (Redis hash)
- [ ] L4 prompt cache (provider native)

### Phase 6: Eval + Feedback (Week 5-6)

- [ ] RAGAS + DeepEval setup
- [ ] Golden dataset (200 câu)
- [ ] Smoke + nightly CI
- [ ] Langfuse prompt mgmt
- [ ] Feedback UI (thumbs)
- [ ] Feedback queue admin

### Phase 7: Channels (Week 6-7)

- [ ] Slack bot (bolt-python)
- [ ] Telegram bot
- [ ] Channel-aware session
- [ ] Multi-channel user merge by email

### Phase 8: Admin + Analytics + Compliance (Week 7)

- [ ] SQLAdmin panel
- [ ] User mgmt, doc mgmt, cost dashboard
- [ ] Metabase setup + dashboards
- [ ] GDPR export/delete endpoints
- [ ] Audit log
- [ ] Backup/restore runbook + drill

### Phase 9: Multimodal + Polish (Week 8)

- [ ] Image upload + Gemini Flash multimodal
- [ ] Localization full (date, number, currency)
- [ ] Onboarding flow + sample prompts
- [ ] Mobile responsive polish
- [ ] Voice input (Web Speech API)
- [ ] Load test (1000 query/day, 100 concurrent)
- [ ] Documentation

---

## 20. Cost Estimate (updated)

### 20.1 Monthly (1000 query/day, 30k/month)

| Item | Calc | Monthly |
|---|---|---|
| LLM input (Haiku 4.5, 3k tok avg) | 90M × $1/M | $90 |
| LLM output (500 tok avg) | 15M × $5/M | $75 |
| Prompt cache savings (60% hit) | -60% on input | -$54 |
| L1 cache savings (20% hit) | -20% all LLM | -$22 |
| Gemini Flash (intent/classify) | low cost | $5 |
| Embedding | 10M × $0.15/M | $1.5 |
| Web search (Tavily, 10% × 3 searches) | 9000 × $5/1000 | $45 |
| OpenAI Moderation | free | $0 |
| Postgres/Redis/SigNoz/Metabase | existing | $0 |
| Langfuse self-host | docker | $0 |
| **Total** | | **~$140/month** |

Trong budget $200/tháng ✅. Buffer cho Sonnet escalation.

### 20.2 One-time

| Item | Cost |
|---|---|
| Initial indexing (10k docs) | $10 |
| Dev/test API usage | $50 |
| Eval golden set creation | $20 |

---

## 21. Risks & Open Questions

### 21.1 Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Data residency VN | **High** | Q1 legal confirm before W2 |
| External user prompt inject | High | 3-layer guardrails + eval |
| LLM cost spike | Med | Quota + cost cap |
| Memory drift | Med | User UI to edit + weekly review |
| VN multi-lang quality | Med | Eval set 200 + model swap |
| Vendor lock-in | Low | LLM gateway pattern |
| Odoo defer = miss internal value | Med | Plan M2 priority |

### 21.2 Open questions (BLOCKING)

| # | Question | Owner | Deadline |
|---|---|---|---|
| Q1 | Data residency VN region? | Legal/CTO | Before W2 |
| Q2 | Chat history retention policy? | Product | Before W2 |
| Q3 | Tavily budget approved? | Manager | Before W5 |
| Q4 | Odoo M2 - models exposed? | Tech lead | Before M2 start |
| Q5 | Compliance audit export format? | Legal | Before M2 |
| Q6 | Slack/Telegram workspace approved? | Manager | Before W6 |
| Q7 | T&C + Privacy Policy ready? | Legal | Before W1 launch |

---

## 22. Tech Stack Summary

```
# Core
Python 3.12
FastAPI 0.115+
LangGraph 0.2+
LlamaIndex (RAG only)
mem0 (memory)
SQLAlchemy 2.0 + asyncpg + Alembic
Pydantic v2
Chainlit (web UI)
Authlib (SSO)
Celery + Redis (queue)
Presidio + langdetect + babel

# Eval & Prompt
RAGAS
DeepEval
Langfuse (self-host)

# Guardrails
OpenAI Moderation API
Gemini Flash (classifier)
Custom VN regex

# Observability
OpenTelemetry
SigNoz (self-host)
Metabase

# Admin
SQLAdmin

# Channels
bolt-python (Slack)
python-telegram-bot

# Tools
Tavily (search)
httpx (web fetch)

# DB
Postgres 16 + pgvector
Redis 7

# Infra
Docker + Dokploy
GitHub Actions
Azure (Postgres + Blob)
```

---

## 23. Definition of Done (per phase)

| Phase | DoD |
|---|---|
| 1 | Login Google, send message, stream response |
| 2 | Upload PDF, ask, get answer with citation |
| 3 | Bot nhớ tên + preference qua sessions |
| 4 | Guardrails block jailbreak in eval, quota works |
| 5 | Bot search web + audit log |
| 6 | Eval suite green >70%, feedback button works |
| 7 | Bot replies in Slack/Telegram with same user identity |
| 8 | Admin can review feedback, export user data (GDPR) |
| 9 | Image upload works, VN localization complete |

---

## 24. Decisions Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-14 | LangGraph over LangChain | Better agent state machine |
| 2026-05-14 | pgvector over Qdrant | Reuse Postgres, <10M chunks |
| 2026-05-14 | Gemini Flash + Haiku 4.5 tier | Cost + VN quality |
| 2026-05-14 | mem0 over custom | Faster MVP |
| 2026-05-14 | Tenant-ready, single tenant runtime | Future-proof, no overhead now |
| 2026-05-14 | L1 + L4 cache only | Simple, 60% of full savings |
| 2026-05-14 | OpenAI Moderation + VN regex + LLM | Free, multi-layer |
| 2026-05-14 | RAGAS + DeepEval | Open source, no vendor lock |
| 2026-05-14 | SQLAdmin for admin panel | Fast, Python native |
| 2026-05-14 | Metabase for analytics | Open source dashboards |
| 2026-05-14 | Defer Odoo to M2 | Reduce MVP risk |
| 2026-05-14 | Defer Zalo + native mobile to M3+ | Out of MVP scope |
| 2026-05-14 | Web + Slack + Telegram MVP | Coverage with low effort |
| 2026-05-14 | Image multimodal MVP (Gemini Flash) | Cheap, useful |
| 2026-05-14 | Voice/video defer | Complexity, cost |

---

**End of document v0.2.**
