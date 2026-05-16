# Runbook: Postgres Restore

## When to use

- Production data corruption
- Accidental deletion
- Disaster recovery drill (monthly)

## Prereqs

- Azure Blob access to `chatbot-backups` container
- `pg_restore` installed
- pgvector extension available on target

## Steps

```bash
# 1. Identify backup
az storage blob list --container-name chatbot-backups --output table

# 2. Download
az storage blob download --container-name chatbot-backups \
    --name "chatbot_2026-05-14_02-00.dump" \
    --file ./restore.dump

# 3. Prepare target DB
psql -h $TARGET_HOST -U postgres -c "CREATE DATABASE chatbot_restore"
psql -h $TARGET_HOST -U postgres -d chatbot_restore -c "CREATE EXTENSION vector"
psql -h $TARGET_HOST -U postgres -d chatbot_restore -c "CREATE EXTENSION \"uuid-ossp\""

# 4. Restore
pg_restore -h $TARGET_HOST -U postgres -d chatbot_restore \
    --jobs=4 --verbose ./restore.dump

# 5. Verify
psql -h $TARGET_HOST -U postgres -d chatbot_restore -c \
    "SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM messages;"

# 6. Switch app
# Update DATABASE_URL in .env, restart app
docker compose restart app worker beat
```

## Monthly drill checklist

- [ ] Restore latest backup to staging
- [ ] Run `make test` against staging
- [ ] Verify pgvector index works
- [ ] Document any issues in `docs/runbooks/drill-log.md`
- [ ] Drop restored DB
