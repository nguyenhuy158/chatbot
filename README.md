# AI Chatbot

Multi-purpose AI chatbot with RAG, long-term memory, tools, and multi-channel support.

**Stack:** Python 3.12 · FastAPI · LangGraph · pgvector · mem0 · Chainlit · Redis · Celery · OpenTelemetry · SigNoz

## Quick Start

```bash
# 1. Setup
cp .env.example .env
# Edit .env with your API keys

# 2. Run with Docker
docker-compose up -d

# 3. Run migrations
docker-compose exec app alembic upgrade head

# 4. Open UI
# Web: http://localhost:8000
# Admin: http://localhost:8000/admin
# Metabase: http://localhost:3000
# SigNoz: http://localhost:3301
```

## Local Development (no Docker)

```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync deps
uv sync

# Start Postgres + Redis
docker-compose up -d postgres redis

# Migrations
uv run alembic upgrade head

# Run dev server
uv run uvicorn app.main:app --reload --port 8000

# Run Celery worker (separate terminal)
uv run celery -A app.workers.celery_app worker --loglevel=info

# Run Celery beat (separate terminal)
uv run celery -A app.workers.celery_app beat --loglevel=info
```

## Project Structure

```
chatbot-scaffold/
├── app/
│   ├── main.py              # FastAPI app entry
│   ├── api/                 # HTTP endpoints
│   │   ├── chat.py
│   │   ├── auth.py
│   │   ├── documents.py
│   │   ├── feedback.py
│   │   ├── user.py          # GDPR + settings
│   │   └── admin.py
│   ├── core/                # Cross-cutting
│   │   ├── config.py        # Settings (pydantic-settings)
│   │   ├── security.py      # JWT, auth
│   │   ├── logging.py       # Structured logging
│   │   ├── telemetry.py     # OpenTelemetry setup
│   │   ├── exceptions.py
│   │   └── deps.py          # FastAPI dependencies
│   ├── db/                  # Database
│   │   ├── session.py
│   │   ├── base.py
│   │   └── models/          # SQLAlchemy models
│   ├── services/            # Business logic
│   │   ├── llm_gateway.py
│   │   ├── rag.py
│   │   ├── memory.py
│   │   ├── guardrails.py
│   │   ├── cache.py
│   │   ├── quota.py
│   │   └── moderation.py
│   ├── agent/               # LangGraph agent
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── prompts.py
│   ├── tools/               # Function calling tools
│   │   ├── base.py
│   │   ├── web_search.py
│   │   ├── web_fetch.py
│   │   └── registry.py
│   ├── workers/             # Celery tasks
│   │   ├── celery_app.py
│   │   ├── ingestion.py
│   │   └── scheduled.py
│   └── schemas/             # Pydantic models
│       ├── chat.py
│       ├── user.py
│       └── document.py
├── alembic/                 # DB migrations
├── tests/                   # Pytest
├── docker/                  # Dockerfile + compose
├── scripts/                 # Helper scripts
├── docs/runbooks/           # Ops runbooks
├── pyproject.toml
├── .env.example
└── docker-compose.yml
```

## Phase Status

| Phase | Status |
|---|---|
| 1. Foundation (auth, chat, LLM gateway) | ✅ Done |
| 2. RAG + citation | ✅ Done |
| 3. Memory + Agent | ✅ Done |
| 4. Guardrails + Quota | ✅ Done |
| 5. Tools + Cache | ✅ Done |
| 6. Eval + Feedback | ✅ Done |
| 7. Channels (Slack/Telegram) | ✅ Done |
| 8. Admin + Analytics | ✅ Done |
| 9. Multimodal + Onboarding + i18n | ✅ Done |

**🎉 All 9 phases complete + Chainlit UI + Production Docker hardening.** ~7-8 weeks of work scaffolded.

## Production Deployment

```bash
# Build image (tagged with git SHA)
make docker-build

# Scan for vulnerabilities
make docker-scan

# Run prod stack (uses docker-compose.prod.yml)
IMAGE_TAG=$(git rev-parse --short HEAD) make up-prod
```

See `docs/runbooks/docker-hardening.md` for the full production checklist.

## Run the UI

```bash
# Inside Docker (recommended)
docker compose up -d
# Open http://localhost:8501

# Or locally
make ui
# Open http://localhost:8501
```

The UI talks to the FastAPI backend at `CHATBOT_API_BASE` (defaults to `http://localhost:8000`).
You'll be redirected to `/auth/login/google` on first visit.

## Phase 9 Usage

```bash
# Upload an image
curl -X POST http://localhost:8000/api/images/upload \
  -H "Cookie: access_token=..." \
  -F "file=@screenshot.png"
# Returns: {"image_id": "<uuid>", ...}

# Describe it via Gemini Flash
curl -X POST http://localhost:8000/api/images/describe \
  -H "Cookie: access_token=..." \
  -d '{"image_id": "<uuid>", "prompt": "Lỗi gì hiện trên màn hình?", "lang": "vi"}'

# Onboarding payload for first-time users (frontend renders empty state)
curl http://localhost:8000/api/me/onboarding?lang=vi
# Returns welcome, sample prompts, capability tour steps

# Chat now auto-detects language — write in EN, get EN; write in VN, get VN
curl -X POST http://localhost:8000/api/chat \
  -d '{"message": "What is our refund policy?"}'   # EN response
curl -X POST http://localhost:8000/api/chat \
  -d '{"message": "Chính sách hoàn tiền là gì?"}'  # VN response
```

## Docs

- Architecture: `docs/architecture.md`
- Runbooks: `docs/runbooks/`
- API: http://localhost:8000/docs (Swagger)

## License

Internal use.
