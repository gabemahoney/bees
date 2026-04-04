#!/bin/bash
# test_runner.sh — Phase-specific setup, then launches the appropriate test runner.
# Phases 1 & 2: run integration.sh (bash-based tests)
# Phases 3 & 4: launch Claude with release-test skill (MCP server tests)
# auto_approve.sh runs in the background (started by entrypoint.sh).
set -euo pipefail

export BUG_SERVER_URL="${BEES_MCP_URL:-http://host.docker.internal:8000}"
PHASE="${PHASE:-1}"

echo "=== Phase ${PHASE} setup ==="

# Configure Claude Code API key if available (env var alone doesn't auto-authenticate)
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "Configuring Claude API key..."
  python3 -c "
import json, pathlib, os
p = pathlib.Path.home() / '.claude.json'
d = json.loads(p.read_text()) if p.exists() else {}
d['apiKey'] = os.environ['ANTHROPIC_API_KEY']
p.write_text(json.dumps(d, indent=2))
print('API key written to .claude.json')
"
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

# Phases 1, 2 & 5: run bash integration tests directly
if [[ "$PHASE" == "1" || "$PHASE" == "2" || "$PHASE" == "5" ]]; then
  echo "=== Starting bash integration tests (Phase ${PHASE}) ==="
  cd /test-repo
  exec bash /test-repo/tests/integration.sh ${START_TEST:-}
fi

# Phases 3 & 4: set up testplans hive and launch Claude
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
