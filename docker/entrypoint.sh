#!/usr/bin/env bash
# Entrypoint — dispatches to the right service based on $1 or $SERVICE.
#
# Services:
#   app    : FastAPI server (uvicorn)
#   worker : Celery worker
#   beat   : Celery beat scheduler
#   ui     : Chainlit web UI
#   migrate: Run alembic upgrade head, then exit
#   shell  : Drop into bash for debugging

set -euo pipefail

SERVICE="${1:-${SERVICE:-app}}"

# Wait for Postgres if DATABASE_URL is set
wait_for_postgres() {
    if [ -z "${DATABASE_URL:-}" ]; then
        return 0
    fi
    # Extract host + port from DATABASE_URL (postgresql+asyncpg://user:pass@host:port/db)
    local host port
    host=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
    port=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]\+\)/.*|\1|p')
    port="${port:-5432}"

    if [ -z "$host" ]; then
        return 0
    fi

    echo "[entrypoint] Waiting for postgres at ${host}:${port}..."
    local attempts=0
    until (echo > /dev/tcp/${host}/${port}) 2>/dev/null; do
        attempts=$((attempts + 1))
        if [ $attempts -gt 60 ]; then
            echo "[entrypoint] Postgres not reachable after 60 attempts. Continuing anyway."
            return 0
        fi
        sleep 1
    done
    echo "[entrypoint] Postgres ready."
}

case "$SERVICE" in
    app)
        wait_for_postgres
        exec uvicorn app.main:app \
            --host 0.0.0.0 \
            --port 8000 \
            --workers "${UVICORN_WORKERS:-2}" \
            --access-log \
            --log-config /app/docker/logging.json 2>/dev/null || \
        exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${UVICORN_WORKERS:-2}"
        ;;

    worker)
        wait_for_postgres
        exec celery -A app.workers.celery_app worker \
            --loglevel="${CELERY_LOGLEVEL:-info}" \
            --concurrency="${CELERY_CONCURRENCY:-4}" \
            --max-tasks-per-child=100
        ;;

    beat)
        # Beat doesn't need postgres directly but we wait so it doesn't fire empty
        wait_for_postgres
        exec celery -A app.workers.celery_app beat \
            --loglevel="${CELERY_LOGLEVEL:-info}"
        ;;

    ui)
        exec chainlit run ui/app.py --host 0.0.0.0 --port 8501 --headless
        ;;

    migrate)
        wait_for_postgres
        exec alembic upgrade head
        ;;

    shell)
        exec /bin/bash
        ;;

    *)
        echo "[entrypoint] Unknown service: $SERVICE"
        echo "[entrypoint] Valid: app | worker | beat | ui | migrate | shell"
        exit 1
        ;;
esac
