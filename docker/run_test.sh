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

# Find testplans hive path using bees CLI (scoped to this repo)
TESTPLANS_PATH=$(cd "${PROJECT_ROOT}" && bees list-hives 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
for h in d.get('hives', []):
    if h['normalized_name'] == 'testplans':
        print(h['path'])
        sys.exit(0)
sys.exit(1)
")
if [[ -z "${TESTPLANS_PATH}" ]]; then
  echo "ERROR: testplans hive not found in ~/.bees/config.json"
  exit 1
fi

# Pull Claude API key — try secrets file, env var, macOS Keychain, Linux keyring
CLAUDE_API_KEY=""
if [[ -r ~/.secrets/anthropic_api_key ]]; then
  CLAUDE_API_KEY=$(cat ~/.secrets/anthropic_api_key)
fi
if [[ -z "${CLAUDE_API_KEY}" ]]; then
  CLAUDE_API_KEY="${ANTHROPIC_API_KEY:-}"
fi
if [[ -z "${CLAUDE_API_KEY}" ]] && command -v security &>/dev/null; then
  CLAUDE_API_KEY=$(security find-generic-password -s "Claude Code" -w 2>/dev/null || true)
  if [[ -z "${CLAUDE_API_KEY}" ]]; then
    CREDS_JSON=$(security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null || true)
    if [[ -n "${CREDS_JSON}" ]]; then
      CLAUDE_API_KEY=$(python3 -c "
import json, sys
d = json.loads(sys.argv[1])
print(d.get('claudeAiOauth', {}).get('accessToken', ''))
" "${CREDS_JSON}" 2>/dev/null || true)
    fi
  fi
fi
if [[ -z "${CLAUDE_API_KEY}" ]] && command -v secret-tool &>/dev/null; then
  CLAUDE_API_KEY=$(secret-tool lookup service "Claude Code" 2>/dev/null || true)
fi
if [[ -z "${CLAUDE_API_KEY}" ]]; then
  echo "ERROR: No Claude API key found. Set ANTHROPIC_API_KEY env var, or run 'claude /login'."
  exit 1
fi

# Detect docker access — use sg docker wrapper if direct access fails (Linux group issue)
if docker info > /dev/null 2>&1; then
  DOCKER_CMD="docker"
elif sg docker -c "docker info" > /dev/null 2>&1; then
  DOCKER_CMD="sg docker -c docker"
else
  echo "ERROR: Docker is not accessible. Start Docker or fix group permissions."
  exit 1
fi

# Wrapper function so the rest of the script can just call `_docker ...`
_docker() {
  if [[ "${DOCKER_CMD}" == "docker" ]]; then
    docker "$@"
  else
    sg docker -c "docker $*"
  fi
}

# Clean up previous runs
tmux kill-session -t "${SESSION}" 2>/dev/null || true
_docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

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
_docker build \
  -f "${SCRIPT_DIR}/Dockerfile.test" \
  --build-arg "BEES_VERSION=${BEES_VERSION}" \
  -t bees-test \
  "${BUILD_CTX}"

echo ""
echo "--- Starting container (Phase ${PHASE}) ---"
_docker run -d \
  --name "${CONTAINER_NAME}" \
  --add-host host.docker.internal:host-gateway \
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
  if _docker exec -u testuser "${CONTAINER_NAME}" tmux has-session -t ci 2>/dev/null; then
    echo "Ready after ${i}s"
    break
  fi
  sleep 2
done

# Create host tmux session that attaches to the container's tmux
# Note: tmux itself doesn't need docker group — only the docker exec inside does
if [[ "${DOCKER_CMD}" == "docker" ]]; then
  tmux new-session -d -s "${SESSION}" \
    "docker exec -it -u testuser ${CONTAINER_NAME} tmux attach -t ci; echo ''; echo '--- Phase ${PHASE} exited. Press Enter to close. ---'; read"
else
  tmux new-session -d -s "${SESSION}" \
    "sg docker -c 'docker exec -it -u testuser ${CONTAINER_NAME} tmux attach -t ci'; echo ''; echo '--- Phase ${PHASE} exited. Press Enter to close. ---'; read"
fi

echo ""
echo "Attach with:"
echo ""
echo "  tmux attach -t ${SESSION}"
echo ""
