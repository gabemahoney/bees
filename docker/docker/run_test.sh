#!/bin/bash
# run_test.sh — builds the Docker image and runs one phase of the bees CI test
# Usage:
#   ./docker/run_test.sh <phase>
#
# Attach with: tmux attach -t bees-ci-<phase>
#
# Environment (required):
#   BEES_VERSION  Version published to test.pypi (set by /ci skill)
#   BEES_MCP_URL  Outer bees MCP server URL (default: http://host.docker.internal:8000)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
PHASE="${1:?Usage: run_test.sh <phase> [start-test-number]}"
START_TEST="${2:-}"
BEES_VERSION="${BEES_VERSION:?BEES_VERSION must be set}"
BEES_MCP_URL="${BEES_MCP_URL:-http://host.docker.internal:8000}"
CONTAINER_NAME="bees-ci-${PHASE}"
SESSION="bees-ci-${PHASE}"

# Find testplans hive path from host bees config
TESTPLANS_PATH=$(python3 - <<'EOF'
import json, sys
with open('/Users/gmahoney/.bees/config.json') as f:
    c = json.load(f)
for scope in c.get('scopes', {}).values():
    for hname, hdata in scope.get('hives', {}).items():
        if hname == 'testplans':
            print(hdata['path'])
            sys.exit(0)
sys.exit(1)
EOF
)
if [[ -z "${TESTPLANS_PATH}" ]]; then
  echo "ERROR: testplans hive not found in ~/.bees/config.json"
  exit 1
fi

# Pull Claude API key from macOS Keychain
CLAUDE_API_KEY=$(security find-generic-password -s "Claude Code" -w 2>/dev/null || true)
if [[ -z "${CLAUDE_API_KEY}" ]]; then
  # Newer Claude Code versions store OAuth credentials as JSON under a different service name
  CREDS_JSON=$(security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null || true)
  if [[ -n "${CREDS_JSON}" ]]; then
    CLAUDE_API_KEY=$(python3 -c "
import json, sys
d = json.loads(sys.argv[1])
print(d.get('claudeAiOauth', {}).get('accessToken', ''))
" "${CREDS_JSON}" 2>/dev/null || true)
  fi
fi
if [[ -z "${CLAUDE_API_KEY}" ]]; then
  echo "ERROR: No Claude Code credentials in Keychain. Run 'claude /login' first."
  exit 1
fi

# Clean up previous runs
tmux kill-session -t "${SESSION}" 2>/dev/null || true
docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

echo ""
echo "=== bees CI — Phase ${PHASE} ==="
echo "Version:      ${BEES_VERSION}"
echo "Bugs server:  ${BEES_MCP_URL}"
echo ""

echo "--- Preparing build context ---"
BUILD_CTX=$(mktemp -d)
trap "rm -rf '${BUILD_CTX}'" EXIT
# Copy project root, dereferencing symlinks so Docker can COPY them
rsync -aL --exclude '.git' --exclude 'dist' --exclude '__pycache__' \
  "${PROJECT_ROOT}/" "${BUILD_CTX}/"

echo "--- Building image ---"
docker build \
  -f "${SCRIPT_DIR}/Dockerfile.test" \
  --build-arg "BEES_VERSION=${BEES_VERSION}" \
  -t bees-test \
  "${BUILD_CTX}"

echo ""
echo "--- Starting container (Phase ${PHASE}) ---"
docker run -d \
  --name "${CONTAINER_NAME}" \
  -e "ANTHROPIC_API_KEY=${CLAUDE_API_KEY}" \
  -e "BEES_MCP_URL=${BEES_MCP_URL}" \
  -e "BEES_VERSION=${BEES_VERSION}" \
  -e "PHASE=${PHASE}" \
  -e "START_TEST=${START_TEST}" \
  -v "${HOME}/.claude.json:/host-claude.json:ro" \
  -v "${HOME}/.claude/settings.json:/host-claude-settings.json:ro" \
  -v "${HOME}/.waggle:/host-waggle:ro" \
  -v "${HOME}/projects/waggle:/opt/waggle:ro" \
  -v "${TESTPLANS_PATH}:/tmp/testplans_host:ro" \
  bees-test

# Wait for tmux inside container to be ready
echo "Waiting for container tmux..."
for i in $(seq 1 60); do
  if docker exec -u testuser "${CONTAINER_NAME}" tmux has-session -t ci 2>/dev/null; then
    echo "Ready after ${i}s"
    break
  fi
  sleep 2
done

# Create host tmux session that attaches to the container's tmux
tmux new-session -d -s "${SESSION}" \
  "docker exec -it -u testuser ${CONTAINER_NAME} tmux attach -t ci; echo ''; echo '--- Phase ${PHASE} exited. Press Enter to close. ---'; read"

echo ""
echo "Attach with:"
echo ""
echo "  tmux attach -t ${SESSION}"
echo ""
