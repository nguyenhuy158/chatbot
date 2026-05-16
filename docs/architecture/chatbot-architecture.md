# AI Chatbot — Architecture Document

**Author:** Huy
**Version:** 0.1 (Draft)
**Date:** 2026-05-14
**Status:** Pre-implementation review

---

## 1. Mục tiêu & Scope

### 1.1 Mục tiêu

Build một AI chatbot **đa năng** phục vụ cả khách hàng external lẫn nhân viên nội bộ, với 3 chế độ hoạt động chính:

| Mode | Mô tả | Audience |
|---|---|---|
| **Customer Support** | FAQ, hỏi đáp sản phẩm, hướng dẫn sử dụng | Khách hàng external |
| **Internal Tool** | Tra cứu policy, SOP, dữ liệu công ty | Nhân viên nội bộ |
| **RAG Q&A** | Hỏi đáp trên kho tài liệu (PDF, Notion, Confluence) | Cả hai (phân quyền) |

### 1.2 Non-goals (tuần 1-4 chưa làm)

- Voice / audio
- Image generation
- Fine-tuning model riêng
- Multi-tenancy (chỉ 1 org)

### 1.3 Success metrics

| Metric | Target W4 | Target M3 |
|---|---|---|
| Response latency p95 | <5s | <3s |
| Answer correctness (human eval) | >70% | >85% |
| User retention (DAU/MAU) | >20% | >40% |
| Cost per query | <$0.005 | <$0.003 |
| Hallucination rate | <15% | <5% |

---

## 2. High-level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CHANNELS                                │
│  Web UI (Chainlit)  │  Slack Bot  │  Telegram Bot  │ Zalo   │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS
                         ▼
┌─────────────────────────────────────────────────────────────┐
│             API GATEWAY (FastAPI + SSO)                      │
│  - OAuth Google/Microsoft                                    │
│  - Rate limiting                                             │
│  - Request validation                                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              ROUTER LAYER (Python)                           │
│  - Detect user type (internal vs external) from JWT          │
│  - Detect intent: FAQ / RAG / Tool-using                     │
│  - Apply role-based context filtering                        │
│  - Inject system prompt theo persona                         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│            LANGGRAPH AGENT (State Machine)                   │
│                                                              │
│   ┌──────────┐    ┌──────────┐    ┌────────────┐           │
│   │ Memory   │◄──►│  Agent   │◄──►│   Tools    │           │
│   │  (mem0)  │    │  Loop    │    │ Dispatcher │           │
│   └──────────┘    └────┬─────┘    └─────┬──────┘           │
│                        │                 │                   │
│                        ▼                 ▼                   │
│                  ┌──────────┐      ┌─────────┐              │
│                  │ LLM Call │      │ Tool    │              │
│                  │ Gateway  │      │ Calls   │              │
│                  └──────────┘      └─────────┘              │
└─────────────────────────────────────────────────────────────┘
       │                  │                    │
       ▼                  ▼                    ▼
┌──────────┐      ┌──────────────┐    ┌──────────────┐
│  LLMs    │      │     RAG      │    │   TOOLS      │
│ Gemini   │      │  LlamaIndex  │    │ - Web search │
│ Claude   │      │  + pgvector  │    │ - Odoo API   │
│          │      │              │    │ - Custom     │
└──────────┘      └──────┬───────┘    └──────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    DATA LAYER                                │
│  Postgres (Azure)  │  Redis  │  Object Storage (PDFs/files)│
│  - pgvector        │  cache  │                              │
│  - chat_history    │  queue  │                              │
│  - memory_store    │         │                              │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│              OBSERVABILITY (OpenTelemetry → SigNoz)          │
│  Logs │ Metrics (cost, tokens) │ Traces (LLM calls) │ Alerts│
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Component Design

### 3.1 API Gateway (FastAPI)

| Concern | Detail |
|---|---|
| Framework | FastAPI 0.115+ |
| Auth | `Authlib` cho OAuth, JWT cookies + refresh token |
| SSO providers | Google Workspace, Microsoft Entra ID |
| Rate limit | `slowapi` — 60 req/min/user, 10 req/min/IP |
| CORS | Whitelist frontend domains |
| Validation | Pydantic v2 models cho mọi endpoint |

**Endpoints chính:**

| Method | Path | Mục đích |
|---|---|---|
| `POST` | `/api/chat` | Streaming chat (SSE) |
| `GET` | `/api/conversations` | Lịch sử conversation của user |
| `DELETE` | `/api/conversations/{id}` | Xóa conversation |
| `POST` | `/api/documents/upload` | Upload PDF/docx cho RAG |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/metrics` | Prometheus metrics (internal) |
| `GET` | `/auth/login/google` | OAuth flow |
| `GET` | `/auth/callback` | OAuth callback |

### 3.2 Router Layer

Logic phân luồng request **trước khi vào agent**:

```python
# Pseudo-code, không phải code thật
def route(request, user):
    role = user.role  # "internal" | "external"
    intent = classify_intent(request.message)  # cheap LLM call (Haiku)

    if role == "external":
        allowed_collections = ["public_docs", "faq"]
        system_prompt = EXTERNAL_PROMPT
    else:
        allowed_collections = ["public_docs", "faq", "internal_sop", "engineering"]
        system_prompt = INTERNAL_PROMPT

    return AgentContext(
        intent=intent,
        rag_filter={"collection__in": allowed_collections},
        system_prompt=system_prompt,
        tools=get_tools_for_role(role),
    )
```

**Quan trọng:** Filter RAG **trong query** (pgvector WHERE clause), không phải post-filter. Tránh leak qua re-ranking.

### 3.3 LangGraph Agent

State machine với các node:

```
┌───────────┐     ┌──────────────┐     ┌───────────┐
│  START    │────►│ load_memory  │────►│  plan     │
└───────────┘     └──────────────┘     └─────┬─────┘
                                              │
            ┌─────────────────────────────────┤
            │                                 │
            ▼                                 ▼
     ┌─────────────┐                  ┌──────────────┐
     │ rag_search  │                  │  tool_call   │
     └──────┬──────┘                  └──────┬───────┘
            │                                 │
            └────────────┬────────────────────┘
                         ▼
                  ┌─────────────┐
                  │  generate   │
                  └──────┬──────┘
                         │
                         ▼
                  ┌─────────────┐
                  │ save_memory │
                  └──────┬──────┘
                         │
                         ▼
                  ┌─────────────┐
                  │    END      │
                  └─────────────┘
```

**Node responsibilities:**

| Node | Input | Output | LLM? |
|---|---|---|---|
| `load_memory` | user_id | relevant memories | No |
| `plan` | query + memory | next action (rag/tool/answer) | Yes (cheap) |
| `rag_search` | query | top-k chunks | No |
| `tool_call` | tool name + args | tool result | No |
| `generate` | context + query | final answer | Yes (main) |
| `save_memory` | conversation | updated mem0 store | Async |

**State schema (LangGraph):**

```python
class AgentState(TypedDict):
    user_id: str
    role: Literal["internal", "external"]
    messages: list[BaseMessage]
    memories: list[Memory]
    rag_results: list[Chunk]
    tool_results: list[ToolResult]
    final_answer: str
    metadata: dict  # tokens, cost, latency
```

### 3.4 LLM Gateway

Wrapper trừu tượng để swap model dễ:

| Tier | Model | Use case | Cost/M in | Cost/M out |
|---|---|---|---|---|
| **Cheap** | Gemini 2.5 Flash | Intent classification, summarization, simple Q&A | $0.30 | $2.50 |
| **Main** | Gemini 2.5 Pro **hoặc** Claude Haiku 4.5 | Default chat response | $1.25 / $1 | $10 / $5 |
| **Hard** | Claude Sonnet 4.6 | Complex reasoning, agent với tool use | $3 | $15 |

**Routing logic:**
- Default: Main tier (Haiku 4.5)
- Có tool calls phức tạp → Sonnet 4.6
- Câu < 50 token, không cần RAG → Flash
- Bật **prompt caching** cho system prompt + RAG context (90% savings)

### 3.5 Memory Layer (mem0)

mem0 tự động extract facts từ conversation và lưu vào pgvector.

**Memory types:**

| Type | Mô tả | TTL | Ví dụ |
|---|---|---|---|
| `factual` | Sự thật về user | Vĩnh viễn | "User works at TechCoop Vietnam" |
| `preference` | Sở thích, style | Vĩnh viễn | "Prefers concise answers in Vietnamese" |
| `context` | Bối cảnh session | 30 ngày | "Currently working on Farmnet RFC" |
| `episodic` | Sự kiện cụ thể | 90 ngày | "Asked about pgvector setup on 2026-05-10" |

**Schema:**

```sql
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(768),
    metadata JSONB,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON memories (user_id, memory_type);
```

**Privacy controls:**
- User có thể xem/xóa memories qua UI `/settings/memory`
- Memories không share giữa users
- PII detection (email, phone, SSN) trước khi lưu — redact hoặc skip

### 3.6 RAG Pipeline

**Ingestion flow:**

```
PDF/DOCX/Notion → Parser → Chunker → Embedder → pgvector
                              │
                              ▼
                         Metadata extractor
                         (collection, ACL, source_url)
```

| Step | Tool | Detail |
|---|---|---|
| Parser | `unstructured` hoặc `pymupdf4llm` | PDF → markdown, giữ structure |
| Chunker | LlamaIndex `SemanticSplitter` | 512 token chunks, overlap 64 |
| Embedder | `gemini-embedding-001` (768d) | Multi-lang VN/EN tốt |
| Storage | pgvector + HNSW index | m=16, ef_construction=64 |

**Retrieval flow:**

```
Query → Rewrite (HyDE) → Embed → pgvector search (top 20)
                                       │
                                       ▼
                              Reranker (cross-encoder)
                                       │
                                       ▼
                                  Top 5 chunks
```

**Schema:**

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection TEXT NOT NULL,
    source_url TEXT,
    title TEXT,
    acl JSONB,  -- {"roles": ["internal"], "users": [...]}
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
CREATE INDEX ON chunks (document_id);
```

### 3.7 Tools (Function Calling)

| Tool | Mô tả | Input | Output |
|---|---|---|---|
| `web_search` | Tavily / Brave Search API | query: str | list[SearchResult] |
| `web_fetch` | Fetch URL content | url: str | str (markdown) |
| `odoo_query` | Query Odoo via XML-RPC | model, domain, fields | list[dict] |
| `get_current_time` | Datetime cho timezone VN | tz: str | datetime |
| `calculator` | Eval math expressions | expr: str | float |

**Tool security:**
- Mỗi tool có **role allowlist** (external user không gọi được `odoo_query`)
- Sandbox cho `calculator` (không `eval()` raw)
- Rate limit per tool per user
- Audit log mọi tool call vào table `tool_audit`

---

## 4. Data Model (Postgres)

```sql
-- Users (sync từ SSO)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    role TEXT NOT NULL CHECK (role IN ('internal', 'external')),
    sso_provider TEXT,
    sso_subject TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ
);

-- Conversations
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content TEXT NOT NULL,
    tool_calls JSONB,
    tokens_input INTEGER,
    tokens_output INTEGER,
    cost_usd NUMERIC(10, 6),
    latency_ms INTEGER,
    model TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON messages (conversation_id, created_at);

-- Tool audit log
CREATE TABLE tool_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    tool_name TEXT,
    input JSONB,
    output JSONB,
    success BOOLEAN,
    error TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 5. Security Model

### 5.1 Threat model

| Threat | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Prompt injection** (user inject "ignore previous instructions") | High | Med | System prompt isolation, output filter, Llama Guard |
| **RAG leak** (external user query internal docs) | High | High | ACL filter in pgvector query, role-based collections |
| **Memory contamination** (user A's data → user B) | Low | High | Strict `user_id` filter, foreign key constraints |
| **API key leak** | Med | High | Secret manager (Azure Key Vault), không hardcode |
| **DDoS via expensive queries** | Med | Med | Rate limit, max token cap, cost budget per user |
| **Data exfiltration via tools** | Low | High | Tool allowlist per role, audit log, output redaction |
| **Cross-tenant data leak (Slack DM → Web)** | Med | High | Channel isolation, separate conversation_id |

### 5.2 Auth flow

```
User → Frontend → /auth/login/google
                       │
                       ▼
                 Google OAuth consent
                       │
                       ▼
              /auth/callback?code=...
                       │
                       ▼
              Exchange code → ID token
                       │
                       ▼
              Verify token, upsert user
                       │
                       ▼
              Issue JWT (access 15min + refresh 7d)
                       │
                       ▼
              Set httpOnly cookie
```

### 5.3 Data classification

| Class | Examples | Storage | Retention |
|---|---|---|---|
| **Public** | FAQ, marketing docs | Postgres unencrypted | Forever |
| **Internal** | SOP, policies | Postgres + ACL | Forever |
| **Confidential** | Customer PII, contracts | Postgres encrypted column | Per policy |
| **Restricted** | Auth tokens, secrets | Key Vault only | Rotated 90d |

### 5.4 PII handling

- Detect PII trong query (regex + Presidio) trước khi gửi LLM cloud
- Option: redact `[EMAIL]`, `[PHONE]` trước khi log
- User có right to delete (GDPR Art. 17 / Vietnam PDPL)
- Memory store có TTL configurable

---

## 6. Channels Integration

### 6.1 Web (Chainlit) — Week 1

- Streaming response via SSE
- Markdown rendering, code highlight
- File upload cho RAG
- Conversation history sidebar

### 6.2 Slack — Week 3-4

- Bot OAuth scopes: `chat:write`, `app_mentions:read`, `im:history`
- Reply trong thread cho `@mention`
- Slash command `/ask`
- Map Slack user → internal user via email

### 6.3 Telegram — Week 4

- python-telegram-bot library
- `/start`, `/help`, `/reset` commands
- Auth qua deep link gắn JWT token

### 6.4 Zalo — Backlog

- Cần Zalo OA account + verified business
- Webhook integration
- Defer cho M2+

---

## 7. Observability

### 7.1 Stack

| Layer | Tool | Purpose |
|---|---|---|
| Instrumentation | OpenTelemetry SDK (Python) | Auto-instrument FastAPI, SQLAlchemy, requests |
| LLM tracing | Langfuse hoặc OpenLLMetry | Token count, cost, prompt/response capture |
| Backend | SigNoz (self-host sẵn của Huy) | Logs + metrics + traces |
| Alerts | SigNoz Alertmanager | Pager qua Slack/email |

### 7.2 Key metrics

| Metric | Type | Alert threshold |
|---|---|---|
| `chat_requests_total` | Counter | — |
| `chat_latency_seconds` | Histogram | p95 > 8s |
| `llm_tokens_total{type=in/out}` | Counter | — |
| `llm_cost_usd_total` | Counter | > $10/day |
| `tool_call_errors_total` | Counter | > 5%/5min |
| `rag_search_no_results_ratio` | Gauge | > 30% |
| `auth_failures_total` | Counter | > 10/min |

### 7.3 Traces

Mỗi request có 1 trace ID propagate qua:
- API gateway
- Router
- LangGraph nodes (mỗi node 1 span)
- LLM API call (input/output captured)
- DB query
- Tool call

---

## 8. Deployment

### 8.1 Infrastructure

| Component | Where | Why |
|---|---|---|
| App (FastAPI) | Docker + Dokploy | Stack quen của Huy |
| Postgres | Azure Postgres Flexible | Sẵn có, đã backup |
| Redis | Docker container | Cache + Celery broker |
| SigNoz | Self-host VPS | Sẵn có |
| Object storage | Azure Blob hoặc MinIO | PDF files, attachments |

### 8.2 CI/CD

- GitHub Actions: lint (ruff) → test (pytest) → build Docker → push ECR
- Dokploy webhook để auto-deploy on `main` push
- Migrations: Alembic
- Rollback strategy: keep last 3 Docker tags

### 8.3 Environments

| Env | Purpose | Data |
|---|---|---|
| `local` | Dev trên Mac | Postgres local |
| `staging` | Test trước prod | Snapshot prod ẩn danh |
| `prod` | Live | Real |

---

## 9. Risks & Open Questions

### 9.1 Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Data residency (VN region required?) | **High** | Confirm với legal trước khi index customer PII |
| External user thấy được internal data via prompt injection | **High** | Tách collection ACL, audit eval bộ test cases |
| LLM cost spike do prompt loop | **Med** | Max iterations=5, max tokens per request=4000 |
| Memory drift (mem0 lưu sai facts) | **Med** | User UI để chỉnh memory, weekly review |
| Multi-lang quality kém với tiếng Việt chuyên ngành | **Med** | Eval set 200 câu VN, swap Gemini ↔ Claude nếu tệ |
| Vendor lock-in (Gemini hoặc Anthropic) | **Low** | LLM gateway pattern, model swap qua config |

### 9.2 Open questions

| # | Câu hỏi | Cần ai trả lời | Deadline |
|---|---|---|---|
| Q1 | Data có bắt buộc lưu VN region không? | Legal / CTO | Trước W2 |
| Q2 | Có cần lưu chat history vĩnh viễn hay TTL? | Product | Trước W2 |
| Q3 | Budget cho Tavily/Brave search API? | Manager | Trước W3 |
| Q4 | Odoo nào được expose qua tool? (Farmnet/Farmlink/all?) | Tech lead | Trước W3 |
| Q5 | Có cần audit trail xuất ra file cho compliance? | Legal | Trước M2 |

---

## 10. Roadmap (Full Scope)

### Phase 1: Foundation (Week 1-2)

- [ ] Repo scaffolding (FastAPI + LangGraph + Alembic)
- [ ] Postgres schema + migrations
- [ ] SSO Google login
- [ ] Basic chat endpoint (no memory, no tools)
- [ ] Chainlit web UI
- [ ] LLM gateway (Gemini + Claude swap)
- [ ] Docker + Dokploy deploy

### Phase 2: RAG (Week 2-3)

- [ ] PDF/DOCX ingestion pipeline
- [ ] pgvector setup + HNSW index
- [ ] Embedding pipeline (Gemini embeddings)
- [ ] Retrieval với reranker
- [ ] Collection ACL filter
- [ ] Upload UI

### Phase 3: Memory + Agent (Week 3-4)

- [ ] mem0 integration
- [ ] LangGraph agent với plan/rag/tool/generate nodes
- [ ] Memory management UI
- [ ] PII redaction

### Phase 4: Tools (Week 4-5)

- [ ] Tool framework
- [ ] Web search (Tavily)
- [ ] Odoo XML-RPC tool
- [ ] Tool audit log
- [ ] Role-based tool allowlist

### Phase 5: Channels (Week 5-6)

- [ ] Slack bot
- [ ] Telegram bot
- [ ] Channel-aware session

### Phase 6: Ops + Hardening (Week 6-7)

- [ ] OpenTelemetry full instrumentation
- [ ] SigNoz dashboards
- [ ] Llama Guard / Lakera output filter
- [ ] Eval suite (200+ test cases)
- [ ] Load test (1000 query/day)
- [ ] Documentation

### Phase 7: Polish (Week 7-8)

- [ ] User feedback (thumbs up/down)
- [ ] Cost reporting dashboard
- [ ] Admin panel
- [ ] Backup/restore runbook

---

## 11. Cost Estimate

### 11.1 Monthly (1000 query/day = 30k/month)

| Item | Quantity | Unit cost | Monthly |
|---|---|---|---|
| LLM input (avg 3k tokens/query, Haiku 4.5) | 90M tokens | $1/M | $90 |
| LLM output (avg 500 tokens/query) | 15M tokens | $5/M | $75 |
| Prompt caching (60% hit rate) | -50% on cached | — | -$50 |
| Embedding (one-time + incremental) | ~10M tokens | $0.15/M | $1.5 |
| Web search (10% queries × 3 searches) | 9000 searches | $5/1000 | $45 |
| Postgres (Azure) | existing | — | $0 (existing) |
| Redis (Docker) | self-host | — | $0 |
| SigNoz | self-host | — | $0 |
| **Total estimated** | | | **~$160/month** |

Trong budget $200/tháng ✅. Có buffer cho upgrade lên Sonnet khi cần.

### 11.2 One-time costs

| Item | Cost |
|---|---|
| Initial document indexing (10k docs) | ~$10 |
| Dev/test API usage | ~$30 |

---

## 12. Definition of Done (per phase)

| Phase | DoD |
|---|---|
| Phase 1 | User login Google, gửi tin nhắn, nhận response streaming |
| Phase 2 | Upload PDF, hỏi và bot answer từ PDF với citation |
| Phase 3 | Bot nhớ tên user, sở thích sau khi tắt mở tab |
| Phase 4 | Bot gọi web search và Odoo, audit log đầy đủ |
| Phase 5 | Bot trả lời trong Slack thread khi @mention |
| Phase 6 | SigNoz dashboard có metrics, eval suite pass 70% |
| Phase 7 | Admin xem cost report, user thumbs down → ticket |

---

## 13. Appendix

### 13.1 Tech stack summary

```
Python 3.12
FastAPI 0.115+
LangGraph 0.2+
LlamaIndex (cho RAG only)
mem0 (memory layer)
SQLAlchemy 2.0 + Alembic
Pydantic v2
Chainlit (web UI)
Authlib (SSO)
OpenTelemetry SDK
pytest + pytest-asyncio
ruff (lint + format)

# DB
Postgres 16 + pgvector
Redis 7

# Infra
Docker + Dokploy
GitHub Actions
SigNoz
Azure (existing)
```

### 13.2 Reference

- LangGraph docs: https://langchain-ai.github.io/langgraph/
- mem0: https://github.com/mem0ai/mem0
- pgvector: https://github.com/pgvector/pgvector
- Chainlit: https://docs.chainlit.io/
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/

### 13.3 Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-14 | Use LangGraph over LangChain | Better state management for agents |
| 2026-05-14 | pgvector over Qdrant | Reuse existing Postgres, <10M chunks OK |
| 2026-05-14 | Gemini Flash as default LLM | Cost + Vietnamese quality |
| 2026-05-14 | mem0 over custom memory | Faster MVP, proven library |

---

**End of document.**
