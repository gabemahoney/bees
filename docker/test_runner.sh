#!/bin/bash
# test_runner.sh — Phase-specific setup, then launches the test runner for the phase in $PHASE.
# Phases 1, 2, 5 & 6 (CLI tests): run integration.sh, which runs only that phase's sections
# Every other phase (3, 4 and any phase added to the plan later): launch Claude with the
#   release-test skill, which reads the phase from the plan
#   (Phase 3 also registers a stdio MCP server, Phase 4 starts and registers an HTTP one)
# auto_approve.sh runs in the background (started by entrypoint.sh).
set -euo pipefail

export BUG_SERVER_URL="${BEES_MCP_URL:-http://host.docker.internal:8473}"

# The phase number run_test.sh passes into the container. Never guessed: without it, nothing runs.
PHASE="${PHASE:-}"
if [[ ! "$PHASE" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: PHASE must be a phase number of test plan b.qi9, got '${PHASE}'. docker/run_test.sh <phase> sets it." >&2
  exit 1
fi
# integration.sh and the release-test skill both read it from the environment
export PHASE

echo "=== Phase ${PHASE} setup ==="

# Configure Claude Code API key when not using OAuth.
# CLAUDE_CODE_OAUTH_TOKEN is read directly from the env by the CLI — skip the
# apiKey embed when it's present (apiKey would override the OAuth token).
if [[ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" && -n "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "Configuring Claude API key..."
  python3 -c "
import json, pathlib, os
p = pathlib.Path.home() / '.claude.json'
d = json.loads(p.read_text()) if p.exists() else {}
d['apiKey'] = os.environ['ANTHROPIC_API_KEY']
p.write_text(json.dumps(d, indent=2))
print('API key written to .claude.json')
"
elif [[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]]; then
  echo "Using CLAUDE_CODE_OAUTH_TOKEN from env (no apiKey embed needed)"
fi

# Phase 3: register bees-stdio MCP server
if [[ "$PHASE" == "3" ]]; then
  echo "Registering bees-stdio MCP server..."
  claude mcp add bees-stdio -- bees serve --stdio
fi

# Phase 4: start HTTP server and register it
if [[ "$PHASE" == "4" ]]; then
  echo "Starting bees HTTP server on port 9000..."
  bees serve --http --port 9000 > /tmp/bees_http.log 2>&1 &
  # Wait for server to be ready
  for i in $(seq 1 10); do
    if curl -sf http://127.0.0.1:9000/health > /dev/null 2>&1; then
      echo "HTTP server ready after ${i}s"
      break
    fi
    sleep 1
  done
  echo "Registering bees-http MCP server..."
  claude mcp add --transport http bees-http http://127.0.0.1:9000/mcp
fi

# Phases 1, 2, 5 & 6: run bash integration tests directly (keep in step with SCRIPT_PHASES in integration.sh)
if [[ "$PHASE" == "1" || "$PHASE" == "2" || "$PHASE" == "5" || "$PHASE" == "6" ]]; then
  echo "=== Starting bash integration tests (Phase ${PHASE}) ==="
  cd /test-repo
  exec bash /test-repo/tests/integration.sh ${START_TEST:-}
fi

# Every other phase (3, 4, ...): set up testplans hive and launch Claude
echo "=== Setting up testplans hive ==="
export TESTPLANS_CONFIG=/tmp/testplans-config.json
mkdir -p /test-repo/tickets/testplans
bees colonize-hive --config "${TESTPLANS_CONFIG}" --name testplans --path /test-repo/tickets/testplans
# Copy ticket files (skip .hive marker, evicted, and cemetery dirs)
find /tmp/testplans_host -maxdepth 1 -mindepth 1 \
  ! -name '.hive' ! -name 'evicted' ! -name 'cemetery' \
  -exec cp -r {} /test-repo/tickets/testplans/ \;
echo "Testplans hive ready."

# Register local bees MCP server using the isolated testplans config
claude mcp add bees -- bees serve --stdio --config "${TESTPLANS_CONFIG}"

echo "=== Starting tests (Phase ${PHASE}) ==="
cd /test-repo
if [[ -n "${START_TEST:-}" ]]; then
  echo "Skipping to test ${START_TEST}"
  exec claude "/release-test ${START_TEST}"
else
  exec claude "/release-test"
fi
