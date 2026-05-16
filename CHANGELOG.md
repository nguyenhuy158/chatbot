# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Repo hygiene: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`
- `.github/` templates: pull request, issue templates, `CODEOWNERS`
- `docs/ROADMAP.md` — M0–M8 milestone plan
- Project restructure: scaffold extracted to repo root, docs grouped under `docs/architecture/` and `docs/runbooks/`

### Changed
- Initial scaffold imported from `chatbot-scaffold-prod.tar.gz` (109 Python files, ~8.5k LOC across 9 phases)

### Security
- `.env` and `.claude/` excluded from version control
- Production Docker hardening checklist captured in `docs/runbooks/docker-hardening.md`

---

## [0.0.0] — 2026-05-16

### Added
- Initial commit of chatbot scaffold (FastAPI + Chainlit + LangGraph + RAG)
- Modules: `api/`, `agent/`, `rag/`, `tools/`, `services/`, `guardrails/`, `memory/`, `multimodal/`, `i18n/`, `channels/`, `analytics/`, `eval/`, `workers/`
- Alembic migrations 0001–0005
- Docker compose dev + prod stacks
- Pytest suite covering smoke, RAG, memory, guardrails, channels, i18n, quota, analytics, eval

[Unreleased]: https://github.com/nguyenhuy158/chatbot/compare/v0.0.0...HEAD
[0.0.0]: https://github.com/nguyenhuy158/chatbot/releases/tag/v0.0.0
