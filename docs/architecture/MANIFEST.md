# Chatbot Deliverables — Bundle Contents

| File | Size | Mô tả |
|---|---|---|
| `chatbot-architecture.md` | 26K | Architecture doc v0.1 (initial draft) |
| `chatbot-architecture-v0.2.md` | 34K | Architecture doc v0.2 — **final, 24 sections, 28 topics** |
| `SCAFFOLD-README.md` | 5.5K | Quick start guide cho scaffold |
| `DOCKER-HARDENING.md` | 4.2K | Production Docker checklist |
| `chatbot-scaffold-prod.tar.gz` | 109K | **Full source code — 109 Python files, ~8.5k LOC, 9 phases + UI + Docker prod** |

## Order to read

1. `chatbot-architecture-v0.2.md` — đọc hiểu thiết kế tổng thể
2. `SCAFFOLD-README.md` — xem cách chạy
3. `DOCKER-HARDENING.md` — checklist trước khi deploy prod
4. Giải nén `chatbot-scaffold-prod.tar.gz` để xem code

## Quick start

```bash
tar xzf chatbot-scaffold-prod.tar.gz
cd chatbot-scaffold
cp .env.example .env  # điền API keys
make install
docker compose up -d
# - FastAPI:  http://localhost:8000/docs
# - UI:       http://localhost:8501
# - Admin:    http://localhost:8000/admin
# - Metabase: http://localhost:3000
```

## Status

- 9/9 phases ✅ complete
- Chainlit UI ✅ wired
- Docker prod hardening ✅ done
- 7 open questions (legal/IT) — see arch doc §21.2

Built: 2026-05-15
