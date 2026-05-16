# Production Docker Hardening

This document covers the production posture of the Docker image and what each
choice gives you. Reference before deploying.

## Image structure

```
python:3.12-slim-bookworm  (base, ~150 MB)
   └── base stage           — runtime system deps only
        └── builder stage   — adds gcc + dev libs to compile wheels
             └── runtime    — copies /opt/venv + /app, drops to non-root
```

Final image: ~600-800 MB (mostly Python packages: torch, langchain, etc.).
Build context: pruned by `.dockerignore` to ~10 MB.

## Hardening features

| Feature | Why |
|---|---|
| **Multi-stage build** | Build tools (gcc, build-essential) never reach the final image |
| **Non-root user** (UID 10001) | Container escape doesn't = root on host |
| **`tini` as PID 1** | Proper signal propagation, zombie reap. `docker stop` actually graceful-shuts |
| **Bytecode stripped** | `__pycache__` removed → smaller image, less attack surface |
| **JSON logging** | Parseable by SigNoz / Loki without regex |
| **Healthcheck baked in** | `docker stop` waits for in-flight requests; orchestrators know real state |
| **Entrypoint dispatch** | One image, services chosen by arg (`app`, `worker`, `beat`, `ui`, `migrate`) |
| **OCI labels** | `org.opencontainers.image.revision` = git SHA for traceability |
| **`.dockerignore`** | `.env`, `.git`, `venv`, `__pycache__` never enter build context |
| **TZ=Asia/Ho_Chi_Minh** | Log timestamps match Vietnam ops, quota reset at midnight VN |
| **Read-only-ish** | `/tmp/chatbot-*` are the only writable paths needed |

## What we do NOT do (and why)

- **No distroless** — we need libc + curl for healthcheck + tesseract for OCR.
  Slim debian is the right trade.
- **No FROM scratch** — Python C extensions need glibc.
- **No `apt upgrade` in image** — pin via base image tag; upgrade by bumping base.
- **No secrets baked in** — all via `.env` / Docker secrets / Vault at runtime.

## Build + scan locally

```bash
make docker-build        # builds chatbot:latest
make docker-scan         # trivy + hadolint
```

Expected output:
- Image size ~600-800 MB
- `id` returns `uid=10001(app) gid=10001(app)` ← non-root confirmed
- Trivy may flag CVEs in base packages; review before each release

## Production deploy

```bash
# Pull pre-built image from registry
IMAGE_TAG=v0.1.0 docker compose -f docker-compose.prod.yml up -d

# Or with k8s / Dokploy — point at the registry image
```

## Service mapping

| Compose service | Container command | Purpose |
|---|---|---|
| `migrate` | `migrate` | Run alembic, exit 0 — runs once before app |
| `app` | `app` | FastAPI uvicorn, port 8000, 4 workers prod |
| `worker` | `worker` | Celery worker, concurrency 4 |
| `beat` | `beat` | Celery scheduler (singleton — never scale >1) |
| `ui` | `ui` | Chainlit, port 8501 |

## Resource limits (prod compose)

| Service | Memory | CPU |
|---|---|---|
| postgres | 2G | (unlimited) |
| app | 2G | 1.5 |
| worker | 1.5G | 1.0 |
| beat | 256M | (light) |
| ui | 512M | (light) |
| redis | 512M | (light) |

Tune based on your actual load. Start here, watch with SigNoz.

## Security checklist before going live

- [ ] `.env` file mode `600`, never in git
- [ ] Registry credentials rotated, no `latest` tag in prod (pin to git SHA)
- [ ] Trivy scan passes HIGH+CRITICAL
- [ ] Hadolint zero warnings on Dockerfile
- [ ] Non-root verified: `docker run --rm chatbot:latest id` → uid 10001
- [ ] Healthcheck returns 200: `curl http://localhost:8000/health`
- [ ] Migrations applied: `docker compose run --rm migrate`
- [ ] DB backups configured (see `docs/runbooks/restore.md`)
- [ ] Postgres password is NOT `chatbot` (the dev default)
- [ ] OAuth redirect URLs use HTTPS only
- [ ] CORS_ORIGINS limited to known frontends
- [ ] `APP_DEBUG=false` and `/docs` /  `/redoc` disabled in prod
- [ ] Cookie `Secure` + `SameSite=Lax` enabled (already set when `APP_ENV=prod`)

## Updates

When a new release is built:
1. CI builds + scans + pushes `chatbot:<git_sha>`
2. Manual: `IMAGE_TAG=<sha> make up-prod`
3. Watch SigNoz for error spike; if green, retire old container
4. Rollback: `IMAGE_TAG=<previous_sha> make up-prod`
