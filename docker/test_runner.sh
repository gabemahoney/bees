#!/bin/bash
# test_runner.sh — Phase-specific setup, then launches the test runner for the phase in $PHASE.
# Phases 1, 2, 5 & 6 (CLI tests): run integration.sh, which runs only that phase's sections
# Every other phase (3, 4 and any phase added to the plan later): run Claude with the
#   release-test skill, which reads the phase from the plan
#   (Phase 3 also registers a stdio MCP server, Phase 4 starts, checks and registers an HTTP one)
# Claude runs headless (claude -p), so it exits when its run is over, and no permission prompt can
# hold it (see run_release_test below).
# This script prints a "TEST RUNNER EXITED: <reason>" line, which /ci handles as a crash, when:
# - a setup command fails (the ERR trap below, set from after the PHASE check until the tests start)
# - Phase 4's HTTP server does not come up
# - a Claude run ends with no result line seen (none printed, or ci_claude_stream.py crashed)
# Any other end without a result line (an invalid PHASE, an error that is not a failing command,
# such as an unset variable, or integration.sh ending without one) gets no such line: only the
# "TEST RUNNER EXITED (status N)" line entrypoint.sh prints after every run, also a crash for /ci.
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

# The ERR trap. Under set -e, a setup command that fails would end the phase with no reason. This
# prints the crash line naming the command, then exits with its status.
# - Like set -e, it does not fire for a command tested by if, while, until, ! or && / ||, nor on
#   `exit`, so the Phase 4 check's own crash line is not followed by a second one.
# - Without set -E, bash does not run it inside a shell function: setup must call none.
# - It is cleared before the tests start: integration.sh and run_release_test report their own ends.
on_setup_error() {
  local status="$1"
  local line="$2"
  local command="$3"
  trap - ERR
  # One line of at most 200 characters: the command may be a multi-line python3 -c
  command="${command//$'\n'/ }"
  if [[ "${#command}" -gt 200 ]]; then
    command="${command:0:200}..."
  fi
  echo "TEST RUNNER EXITED: Phase ${PHASE} setup failed at docker/test_runner.sh line ${line}, so no test ran: '${command}' exited with status ${status}"
  exit "${status}"
}
trap 'on_setup_error "$?" "$LINENO" "$BASH_COMMAND"' ERR

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

# Phase 4: start HTTP server, check that it answers, and register it
if [[ "$PHASE" == "4" ]]; then
  echo "Starting bees HTTP server on port 9000..."
  bees serve --http --port 9000 > /tmp/bees_http.log 2>&1 &
  HTTP_SERVER_PID=$!
  # Claude must not start without the server: it would find no bees-http tools and give up.
  # check_bees_server.py sends an MCP initialize, so a server that is up but broken fails too.
  # Retry only while nothing listens and the server process runs, for up to HTTP_SERVER_WAIT s.
  HTTP_SERVER_URL="http://127.0.0.1:9000"
  HTTP_SERVER_WAIT=30
  HTTP_SERVER_READY=""
  HTTP_SERVER_ERROR=""
  for i in $(seq 1 "${HTTP_SERVER_WAIT}"); do
    CHECK_STATUS=0
    CHECK_OUTPUT=$(python3 /usr/local/bin/check_bees_server.py "${HTTP_SERVER_URL}" 2>&1) || CHECK_STATUS=$?
    if [[ "${CHECK_STATUS}" -eq 0 ]]; then
      HTTP_SERVER_READY=1
      echo "HTTP server ready after ${i}s: ${CHECK_OUTPUT}"
      break
    fi
    if [[ "${CHECK_STATUS}" -ne 1 ]]; then
      # Something answers, but not as a bees MCP server: waiting will not change that
      HTTP_SERVER_ERROR="${CHECK_OUTPUT}"
      break
    fi
    if ! kill -0 "${HTTP_SERVER_PID}" 2>/dev/null; then
      SERVER_STATUS=0
      wait "${HTTP_SERVER_PID}" || SERVER_STATUS=$?
      HTTP_SERVER_ERROR="the bees serve process exited with status ${SERVER_STATUS}"
      break
    fi
    HTTP_SERVER_ERROR="no answer within ${HTTP_SERVER_WAIT} s (${CHECK_OUTPUT})"
    sleep 1
  done
  if [[ -z "${HTTP_SERVER_READY}" ]]; then
    echo "--- /tmp/bees_http.log (last 20 lines) ---"
    tail -n 20 /tmp/bees_http.log 2>/dev/null || true
    echo "--- ~/.bees/mcp.log (last 20 lines) ---"
    tail -n 20 ~/.bees/mcp.log 2>/dev/null || echo "(no ~/.bees/mcp.log)"
    echo "TEST RUNNER EXITED: Phase 4 setup failed, so Claude was not started: the bees HTTP server did not come up at ${HTTP_SERVER_URL}: ${HTTP_SERVER_ERROR}. Its logs are above."
    exit 1
  fi
  echo "Registering bees-http MCP server..."
  claude mcp add --transport http bees-http http://127.0.0.1:9000/mcp
fi

# Phases 1, 2, 5 & 6: run bash integration tests directly (keep in step with SCRIPT_PHASES in integration.sh)
if [[ "$PHASE" == "1" || "$PHASE" == "2" || "$PHASE" == "5" || "$PHASE" == "6" ]]; then
  echo "=== Starting bash integration tests (Phase ${PHASE}) ==="
  cd /test-repo
  # Setup is over: integration.sh reports its own end
  trap - ERR
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

# Runs Claude headless with the prompt in $1 and reports how the run ended. An interactive session
# sits at its prompt once the run is over, so a run that gave up without a result line held the
# phase until /ci's deadline; claude -p exits instead. ci_claude_stream.py shows the run in this
# pane as it happens, then repeats the result lines it saw (RELEASE TEST PHASE N PASSED,
# BUG FILED:, BUG FILING FAILED:) as the last lines. With none, it exits 1, and this prints a
# TEST RUNNER EXITED line with Claude's exit status and how the run ended, and returns 1. Any
# other status means ci_claude_stream.py crashed, so whether Claude printed a result line is not
# known: the TEST RUNNER EXITED line says so, and this returns 1 too.
# Nothing can answer a prompt here (stdin is /dev/null), so anything that would prompt is denied,
# and a strict test runner takes a denial for a bug. Some commands prompt even with Bash allowed
# (e.g. a redirect to a ~ path); auto_approve.sh used to approve them. So permissions are skipped:
# Claude Code's documented setup for unattended runs in a container as a non-root user (testuser).
# The deny rules in docker/claude-settings.json still apply.
run_release_test() {
  local prompt="$1"
  local outcome_file=/tmp/release_test_outcome.txt
  local -a statuses
  local outcome
  rm -f "${outcome_file}"
  set +e
  claude -p "${prompt}" --output-format stream-json --verbose --dangerously-skip-permissions < /dev/null \
    | python3 /usr/local/bin/ci_claude_stream.py --phase "${PHASE}" --outcome-file "${outcome_file}"
  statuses=("${PIPESTATUS[@]}")
  set -e
  if [[ "${statuses[1]}" -eq 0 ]]; then
    return 0
  fi
  if [[ "${statuses[1]}" -ne 1 ]]; then
    echo "TEST RUNNER EXITED: ci_claude_stream.py crashed (status ${statuses[1]}), so whether Claude printed a result line is not known (claude exit status ${statuses[0]}). Its error and the run so far are above."
    return 1
  fi
  outcome=$(cat "${outcome_file}" 2>/dev/null || true)
  if [[ -z "${outcome}" ]]; then
    outcome="ci_claude_stream.py exited with status 1 before it could say how the run ended"
  fi
  echo "TEST RUNNER EXITED: Claude ended without printing a result line (claude exit status ${statuses[0]}): ${outcome}"
  return 1
}

echo "=== Starting tests (Phase ${PHASE}) ==="
cd /test-repo
RELEASE_TEST_PROMPT="/release-test"
if [[ -n "${START_TEST:-}" ]]; then
  echo "Skipping to test ${START_TEST}"
  RELEASE_TEST_PROMPT="/release-test ${START_TEST}"
fi
# Setup is over: run_release_test reports its own end. Under set -e, a run without a result line
# ends the script with status 1.
trap - ERR
run_release_test "${RELEASE_TEST_PROMPT}"
