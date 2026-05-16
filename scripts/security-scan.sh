#!/usr/bin/env bash
# Scan the local docker image for vulnerabilities + Dockerfile lint.
#
# Requires: trivy + hadolint on PATH (brew install trivy hadolint).
# In CI we run these from official actions instead.

set -euo pipefail

IMAGE="${1:-chatbot:latest}"

echo "==> hadolint Dockerfile"
if command -v hadolint >/dev/null 2>&1; then
    hadolint docker/Dockerfile || true
else
    echo "hadolint not installed, skipping. brew install hadolint"
fi

echo ""
echo "==> trivy image scan (HIGH+CRITICAL only)"
if command -v trivy >/dev/null 2>&1; then
    trivy image \
        --severity HIGH,CRITICAL \
        --ignore-unfixed \
        --no-progress \
        "$IMAGE"
else
    echo "trivy not installed, skipping. brew install trivy"
fi

echo ""
echo "==> Image size"
docker image ls --format "{{.Repository}}:{{.Tag}} {{.Size}}" | grep "$IMAGE" || true

echo ""
echo "==> Check non-root"
docker run --rm --entrypoint "" "$IMAGE" id
