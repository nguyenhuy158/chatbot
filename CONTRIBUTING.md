# Contributing

This repository is proprietary (see `LICENSE`). External contributions are not accepted by default. Internal collaborators and authorized contractors should follow the workflow below.

## Prerequisites

- Python 3.11+
- Docker + Docker Compose
- `make`, `git`
- Access to repo secrets (env vars in `.env`)

## Local setup

```bash
git clone git@github.com:nguyenhuy158/chatbot.git
cd chatbot
cp .env.example .env          # fill in secrets
pip install -e ".[dev]"
docker compose up -d postgres redis qdrant
alembic upgrade head
pytest tests/test_smoke.py
```

See `docs/ROADMAP.md` for milestone context.

## Branching

- `main` — protected, always deployable. No direct pushes.
- `feat/<short-slug>` — new features
- `fix/<short-slug>` — bug fixes
- `chore/<short-slug>` — tooling, docs, refactors with no behavior change
- `hotfix/<short-slug>` — urgent prod fix, branched from `main`

Keep branches short-lived (< 3 days). Rebase on `main` before opening PR.

## Commit style

Conventional Commits:

```
<type>(<scope>): <subject>

[body — why, not what]
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, `build`, `ci`.

Examples:

```
feat(rag): add bge-reranker-v2 to retrieval pipeline
fix(quota): correct daily reset boundary in Asia/Ho_Chi_Minh
chore(deps): bump fastapi to 0.115
```

Subject ≤ 50 chars. Body wrap at 72.

## Pull requests

1. Open PR against `main`. Fill the template.
2. Link related issue or roadmap milestone (`docs/ROADMAP.md` M-X).
3. CI must pass: `ruff`, `pytest`, eval gate (`app/eval/cli.py`).
4. At least 1 reviewer approval from `CODEOWNERS`.
5. Squash-merge. Delete branch after merge.

### PR checklist

- [ ] Tests added or updated
- [ ] `docs/` updated if behavior, env vars, or API changed
- [ ] No secrets in diff
- [ ] Migration added if schema changed (`alembic revision -m "..."`)
- [ ] Runbook entry added if ops behavior changed

## Code style

- Format: `ruff format .`
- Lint: `ruff check .`
- Type-check: `mypy app/`
- Tests: `pytest`

Pre-commit hook recommended (`pip install pre-commit && pre-commit install`).

## Tests

- Unit + integration tests live in `tests/`
- Smoke test must pass on every PR: `pytest tests/test_smoke.py`
- New feature → new test. No silent feature additions.
- Eval regression on golden datasets fails CI (see M4 in `docs/ROADMAP.md`).

## Security

Never commit secrets. Use `.env` (gitignored). Report vulnerabilities per `SECURITY.md` — do not file public issues.

## Questions

Open a GitHub issue with the `question` label, or contact the repo owner directly.
