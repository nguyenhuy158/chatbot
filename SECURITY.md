# Security Policy

## Supported versions

Only the latest commit on `main` is supported. No backports.

## Reporting a vulnerability

**Do not file public GitHub issues for security bugs.**

Email the repository owner via the GitHub profile contact:
https://github.com/nguyenhuy158

Or open a [GitHub security advisory](https://github.com/nguyenhuy158/chatbot/security/advisories/new) (preferred — private by default).

Include:

- Affected component (file path, endpoint, or feature)
- Reproduction steps or proof of concept
- Impact assessment (data exposure, privilege escalation, DoS, etc.)
- Suggested remediation if known

## Response SLA

| Severity | Acknowledge | Fix target |
|----------|-------------|------------|
| Critical (RCE, auth bypass, data exfiltration) | 24 h | 7 days |
| High (privilege escalation, sensitive data leak) | 3 days | 30 days |
| Medium (info disclosure, CSRF, stored XSS) | 7 days | 60 days |
| Low (rate-limit gaps, hardening) | 14 days | next release |

## Scope

In scope:

- This repository's code (`app/`, `ui/`, `scripts/`, `docker/`, `alembic/`)
- Deployed instances operated by the repo owner
- Default Docker images built from `docker/Dockerfile`

Out of scope:

- Third-party dependencies (report upstream)
- Social engineering, physical access, denial of service via volume
- Findings from automated scanners without working PoC
- Issues in forks or modified deployments

## Safe harbor

Good-faith research that follows this policy will not result in legal action. Do not:

- Access, modify, or destroy data that is not your own
- Disrupt service for other users
- Publicly disclose before coordinated fix release

## Hardening references

- `docs/runbooks/docker-hardening.md` — production Docker checklist
- `scripts/security-scan.sh` — local scan helper
- `app/core/security.py` — auth, CSRF, session handling
- `app/guardrails/` — input moderation
