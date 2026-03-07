#!/bin/bash
set -euo pipefail

# === CONFIGURATION ===
REPO=/test-repo
TEST_NUM=0
PASS_COUNT=0
FAIL_COUNT=0
START_TEST="${1:-0}"

# Environment guard
[ -d "$REPO" ] || { echo "Must run inside Docker at /test-repo"; exit 1; }

# BUG_SERVER_URL for fail_test
BUG_SERVER_URL="${BUG_SERVER_URL:-http://host.docker.internal:8000}"

# Shared state for capture_cmd
CMD_OUT=""
CMD_EXIT=0

# === HELPER FUNCTIONS ===

pass_test() {
    local name="$1"
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "[PASS] Test $TEST_NUM: $name"
}

fail_test() {
    local name="$1"
    local reason="$2"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    echo "[FAIL] Test $TEST_NUM: $reason"
    local bug_out
    bug_out=$(python3 "$REPO/docker/file_bug.py" \
        --url "$BUG_SERVER_URL/mcp" \
        --title "CI Test $TEST_NUM: $name" \
        --description "$reason" 2>&1) || true
    echo "$bug_out"
    exit 1
}

run_test() {
    local fn="$1"
    TEST_NUM=$((TEST_NUM + 1))
    if [ "$TEST_NUM" -lt "$START_TEST" ]; then
        return
    fi
    "$fn"
}

check_json() {
    local json_str="$1"
    local filter="$2"
    echo "$json_str" | python3 -c "import sys,json; d=json.load(sys.stdin); print($filter)"
}

assert_eq() {
    local got="$1"
    local expected="$2"
    local name="$3"
    local reason="${4:-expected '$expected' but got '$got'}"
    if [ "$got" = "$expected" ]; then
        pass_test "$name"
    else
        fail_test "$name" "$reason"
    fi
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    local name="$3"
    local reason="${4:-output does not contain '$needle'}"
    if echo "$haystack" | grep -qF "$needle"; then
        pass_test "$name"
    else
        fail_test "$name" "$reason"
    fi
}

assert_no_traceback() {
    local output="$1"
    local name="$2"
    if echo "$output" | grep -qF "Traceback (most recent call last)"; then
        fail_test "$name" "Python traceback detected in output"
    fi
}

capture_cmd() {
    CMD_EXIT=0
    CMD_OUT=$("$@" 2>&1) || CMD_EXIT=$?
}

# === PHASE 1: INSTALLATION ===

test_install_bees() {
    capture_cmd pip install /src
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Install bees CLI" "pip install /src failed (exit $CMD_EXIT)"
    fi
    assert_no_traceback "$CMD_OUT" "Install bees CLI"
    command -v bees > /dev/null 2>&1 || fail_test "Install bees CLI" "bees not found on PATH"
    pass_test "Install bees CLI"
}

test_bees_help() {
    capture_cmd bees --help
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "bees --help" "bees --help failed (exit $CMD_EXIT)"
    fi
    assert_no_traceback "$CMD_OUT" "bees --help"
    if ! echo "$CMD_OUT" | grep -qF "Bees ticket management CLI"; then
        fail_test "bees --help" "output does not mention 'Bees ticket management CLI'"
    fi
    pass_test "bees --help"
}

test_config_bootstrap() {
    capture_cmd bees list-hives --test-config
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Config bootstrap" "bees list-hives --test-config failed (exit $CMD_EXIT)"
    fi
    assert_no_traceback "$CMD_OUT" "Config bootstrap"
    local status
    status=$(check_json "$CMD_OUT" "d['status']")
    if [ "$status" != "success" ]; then
        fail_test "Config bootstrap" "Expected status=success, got status=$status"
    fi
    pass_test "Config bootstrap"
}

run_test test_install_bees
run_test test_bees_help
run_test test_config_bootstrap

# === PHASE 2 tests will be appended here ===

# === SUCCESS SIGNAL ===
echo ""
echo "=========================================="
echo "RELEASE TEST PHASE 2 PASSED"
echo "=========================================="
echo "Tests passed: $PASS_COUNT / $TEST_NUM"
