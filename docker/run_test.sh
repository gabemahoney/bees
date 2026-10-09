#!/bin/bash
# run_test.sh — builds the Docker image and runs one phase of the bees CI test
# Usage:
#   ./docker/run_test.sh <phase>
#
# Attach with: tmux attach -t bees-ci-<phase>
#
# Environment:
#   BEES_VERSION  (required) Version published to test.pypi (set by /ci skill)
#   BEES_CI_PORT  Host port of the outer bees HTTP server that the containers
#                 file bugs against (default: 8473)
#   BEES_MCP_URL  Outer bees server URL as seen from the container
#                 (default: http://host.docker.internal:${BEES_CI_PORT}).
#                 An override must include an explicit port (e.g. http://myhost:8473):
#                 the identity check below always probes it and rejects a URL without one.
#   BEES_REPO_ROOT  Host directory the outer bees server picks this repo's hives by
#                 (default: this checkout). Passed on with symlinks resolved: the
#                 bees CLI run from there lists the same hives the server sees for it.
#   BEES_BUGS_HIVE  Hive the containers file bugs into (default: picked from
#                 'bees list-hives' run from BEES_REPO_ROOT by docker/ci_bugs_hive.py:
#                 in the most specific scope matching BEES_REPO_ROOT that has one, the
#                 hive named "bugs", else the only hive whose name contains "bugs").
#                 With no such hive, the script stops before the phase starts.
#   BEES_REPO_ROOT and BEES_BUGS_HIVE reach the container as env vars, where
#   docker/file_bug.py files bugs with them.
#
# Test plan: the phases run plan b.qi9 from this checkout's testplans hive copy
# (docker/testplans), mounted into the container. It is not looked up among the host's
# registered hives, whose "testplans" may be another checkout's copy or another repo's hive.
# /ci reads the same copy (docker/ci_plan.py), and records phase statuses only into it.
#
# Server identity checks (docker/check_bees_server.py: an MCP initialize that must
# report serverInfo.name "bees"; /health is not enough, another service may answer it):
#   1. Host side, only with the default BEES_MCP_URL, before the image build so it
#      fails fast. It probes the address bees must listen on, printed by
#      docker/ci_bind_host.py: the Docker bridge gateway on Linux Docker Engine,
#      127.0.0.1 on Docker Desktop.
#   2. From a container, always (also when BEES_MCP_URL is set). After the build, a
#      throwaway container with the phase container's host mapping probes BEES_MCP_URL,
#      so the check sees the exact server the tests will use. This one is definitive.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
PHASE="${1:?Usage: run_test.sh <phase> [start-test-number]}"
START_TEST="${2:-}"
BEES_VERSION="${BEES_VERSION:?BEES_VERSION must be set}"
BEES_CI_PORT="${BEES_CI_PORT:-8473}"
CONTAINER_NAME="bees-ci-${PHASE}"
SESSION="bees-ci-${PHASE}"

# How containers reach the host. The phase container and the identity probe share it.
ADD_HOST_ARGS=(--add-host host.docker.internal:host-gateway)

USING_DEFAULT_MCP_URL=""
if [[ -z "${BEES_MCP_URL:-}" ]]; then
  BEES_MCP_URL="http://host.docker.internal:${BEES_CI_PORT}"
  USING_DEFAULT_MCP_URL=1
fi

# The test plan the phases run: this checkout's copy of the testplans hive
TEST_PLAN_ID="b.qi9"
TESTPLANS_PATH="${PROJECT_ROOT}/docker/testplans"
if [[ ! -f "${TESTPLANS_PATH}/${TEST_PLAN_ID}/${TEST_PLAN_ID}.md" ]]; then
  echo "ERROR: test plan ${TEST_PLAN_ID} not found in ${TESTPLANS_PATH} (no ${TEST_PLAN_ID}/${TEST_PLAN_ID}.md there)."
  echo "The phases run the plan from this checkout's docker/testplans: restore it there."
  exit 1
fi

# The repo root the host's bees server picks this repo's hives by. The bees CLI resolves symlinks
# in its working directory, so the root is passed on resolved: the server then sees the same hives.
REPO_ROOT_SETTING="${BEES_REPO_ROOT:-${PROJECT_ROOT}}"
if ! BEES_REPO_ROOT=$(cd "${REPO_ROOT_SETTING}" && pwd -P); then
  echo "ERROR: BEES_REPO_ROOT is not a directory on this host: ${REPO_ROOT_SETTING}"
  exit 1
fi

# Find the bugs hive that failing tests file into, among the host's hives for the repo root
if [[ -z "${BEES_BUGS_HIVE:-}" ]]; then
  if ! HIVES_JSON=$(cd "${BEES_REPO_ROOT}" && bees list-hives 2>/dev/null); then
    echo "ERROR: 'bees list-hives' failed in ${BEES_REPO_ROOT}. Install bees on the host, fix BEES_REPO_ROOT, or set BEES_BUGS_HIVE."
    # bees reports its errors as JSON on stdout
    if [[ -n "${HIVES_JSON}" ]]; then
      echo "bees list-hives output: ${HIVES_JSON}"
    fi
    exit 1
  fi
  if ! BEES_BUGS_HIVE=$(python3 "${SCRIPT_DIR}/ci_bugs_hive.py" --repo-root "${BEES_REPO_ROOT}" <<< "${HIVES_JSON}"); then
    echo "ERROR: no bugs hive found for ${BEES_REPO_ROOT} (reason above)."
    echo "Set BEES_BUGS_HIVE to the hive the CI containers should file bugs into."
    exit 1
  fi
fi

# Pull Claude auth — prefer OAuth token (Max subscription), fall back to API key
CLAUDE_OAUTH_TOKEN=""
if [[ -r ~/.secrets/claude_oauth_token ]]; then
  CLAUDE_OAUTH_TOKEN=$(cat ~/.secrets/claude_oauth_token | tr -d '[:space:]')
fi
if [[ -z "${CLAUDE_OAUTH_TOKEN}" ]]; then
  CLAUDE_OAUTH_TOKEN="${CLAUDE_CODE_OAUTH_TOKEN:-}"
fi

CLAUDE_API_KEY=""
if [[ -z "${CLAUDE_OAUTH_TOKEN}" ]]; then
  # Fall back to API key if no OAuth token available
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
    echo "ERROR: No Claude auth found. Set CLAUDE_CODE_OAUTH_TOKEN, ANTHROPIC_API_KEY, or run 'claude setup-token'."
    exit 1
  fi
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

# Check 1 (host side, default BEES_MCP_URL only): bees must listen where host.docker.internal leads.
BIND_HOST=""
if [[ -n "${USING_DEFAULT_MCP_URL}" ]]; then
  BRIDGE_JSON=$(_docker network inspect bridge 2>/dev/null || true)
  BIND_HOST=$(python3 "${SCRIPT_DIR}/ci_bind_host.py" <<< "${BRIDGE_JSON}")
  if ! python3 "${SCRIPT_DIR}/check_bees_server.py" "http://${BIND_HOST}:${BEES_CI_PORT}"; then
    echo "ERROR: no bees HTTP server confirmed at ${BIND_HOST}:${BEES_CI_PORT}, the address the containers reach."
    echo "Start one with 'bees serve --http --host ${BIND_HOST} --port ${BEES_CI_PORT}', or set BEES_CI_PORT to a free port and start bees there."
    exit 1
  fi
fi

# Clean up previous runs
tmux kill-session -t "${SESSION}" 2>/dev/null || true
_docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

echo ""
echo "=== bees CI — Phase ${PHASE} ==="
echo "Version:      ${BEES_VERSION}"
echo "Bugs server:  ${BEES_MCP_URL}"
echo "Bugs hive:    ${BEES_BUGS_HIVE}"
echo "Repo root:    ${BEES_REPO_ROOT}"
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
echo "--- Checking the bees server from a container ---"
# Check 2 (definitive): a host-side check can pass while the containers reach another service, or
# nothing, at BEES_MCP_URL. Exit codes are those of check_bees_server.py; others come from docker.
PROBE_STATUS=0
_docker run --rm "${ADD_HOST_ARGS[@]}" --entrypoint python3 bees-test \
  /usr/local/bin/check_bees_server.py "${BEES_MCP_URL}" || PROBE_STATUS=$?
if [[ "${PROBE_STATUS}" -ne 0 ]]; then
  echo "ERROR: no bees HTTP server confirmed at ${BEES_MCP_URL} from inside a container."
  case "${PROBE_STATUS}" in
    1)
      if [[ -n "${BIND_HOST}" ]]; then
        echo "bees answers on the host at ${BIND_HOST}:${BEES_CI_PORT}, but the containers cannot reach it."
        echo "A host firewall may be blocking container-to-host traffic on port ${BEES_CI_PORT}, or host.docker.internal does not lead to ${BIND_HOST} on this host (see the bind host line above)."
      else
        echo "Nothing is listening there as seen from a container. Start bees where BEES_MCP_URL leads, or fix BEES_MCP_URL."
      fi
      ;;
    2)
      echo "The connection was not refused, but no bees MCP server answered (reason above)."
      echo "On a timeout, a host firewall may be dropping container-to-host traffic on that port. Otherwise another service answers there: start bees on a free BEES_CI_PORT, or fix BEES_MCP_URL."
      ;;
    3)
      echo "BEES_MCP_URL must be an http:// or https:// URL with a host and a port from 1 to 65535."
      ;;
    *)
      echo "The check container failed to run (docker exit ${PROBE_STATUS})."
      ;;
  esac
  exit 1
fi

echo ""
echo "--- Starting container (Phase ${PHASE}) ---"
AUTH_ENV_ARGS=()
if [[ -n "${CLAUDE_OAUTH_TOKEN}" ]]; then
  AUTH_ENV_ARGS+=(-e "CLAUDE_CODE_OAUTH_TOKEN=${CLAUDE_OAUTH_TOKEN}")
  echo "Auth: using Claude Max OAuth token"
elif [[ -n "${CLAUDE_API_KEY}" ]]; then
  AUTH_ENV_ARGS+=(-e "ANTHROPIC_API_KEY=${CLAUDE_API_KEY}")
  echo "Auth: using Anthropic API key"
fi

# No host Claude config file is mounted: the container gets only the auth env vars above.
# entrypoint.sh builds the container's .claude.json from them, and installs the Claude settings
# copied into the image (docker/claude-settings.json).
_docker run -d \
  --name "${CONTAINER_NAME}" \
  "${ADD_HOST_ARGS[@]}" \
  "${AUTH_ENV_ARGS[@]}" \
  -e "BEES_MCP_URL=${BEES_MCP_URL}" \
  -e "BEES_BUGS_HIVE=${BEES_BUGS_HIVE}" \
  -e "BEES_REPO_ROOT=${BEES_REPO_ROOT}" \
  -e "BEES_VERSION=${BEES_VERSION}" \
  -e "PHASE=${PHASE}" \
  -e "START_TEST=${START_TEST}" \
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
