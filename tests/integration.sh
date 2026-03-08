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
cd "$REPO"

# BUG_SERVER_URL for fail_test
BUG_SERVER_URL="${BUG_SERVER_URL:-http://host.docker.internal:8000}"

# Shared state for capture_cmd
CMD_OUT=""
CMD_ERR=""
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
    bug_out=$(python3 /usr/local/bin/file_bug.py \
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
    # Check both stdout and stderr for Python tracebacks
    if echo "$output" | grep -qF "Traceback (most recent call last)"; then
        fail_test "$name" "Python traceback detected in stdout"
    fi
    if echo "$CMD_ERR" | grep -qF "Traceback (most recent call last)"; then
        fail_test "$name" "Python traceback detected in stderr"
    fi
}

capture_cmd() {
    CMD_EXIT=0
    local _err_file
    _err_file=$(mktemp)
    CMD_OUT=$("$@" 2>"$_err_file") || CMD_EXIT=$?
    CMD_ERR=$(cat "$_err_file")
    rm -f "$_err_file"
}

# === PHASE 1: INSTALLATION ===

test_install_bees() {
    # In Docker CI, bees is pre-installed from test.pypi. Verify it's on PATH.
    command -v bees > /dev/null 2>&1 || fail_test "bees CLI installed" "bees not found on PATH"
    capture_cmd pip show bees-md
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "bees CLI installed" "pip show bees-md failed (exit $CMD_EXIT)"
    fi
    assert_no_traceback "$CMD_OUT" "bees CLI installed"
    pass_test "bees CLI installed"
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
    local hive_count
    hive_count=$(check_json "$CMD_OUT" "len(d.get('hives', []))")
    if [ "$hive_count" != "0" ]; then
        fail_test "Config bootstrap" "Expected empty hives, got $hive_count"
    fi
    pass_test "Config bootstrap"
}

run_test test_install_bees
run_test test_bees_help
run_test test_config_bootstrap

# === PHASE 2 GROUP A: HIVE MANAGEMENT ===

test_hm_colonize_with_tiers() {
    capture_cmd bees colonize-hive \
        --name "Test Hive" \
        --path "$REPO/tickets/test_hive" \
        --child-tiers '{"t1":["Task","Tasks"],"t2":["Subtask","Subtasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Colonize hive with tiers" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Colonize hive with tiers"
    local nname
    nname=$(check_json "$CMD_OUT" "d['normalized_name']")
    if [ "$nname" != "test_hive" ]; then
        fail_test "Colonize hive with tiers" "Expected normalized_name=test_hive, got $nname"
    fi
    pass_test "Colonize hive with tiers"
}

test_hm_list_one() {
    capture_cmd bees list-hives
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "List hives shows Test Hive" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "List hives shows Test Hive"
    local found
    found=$(check_json "$CMD_OUT" "'Test Hive' in [h['display_name'] for h in d.get('hives',[])]")
    if [ "$found" != "True" ]; then
        fail_test "List hives shows Test Hive" "Test Hive not found in hive list"
    fi
    pass_test "List hives shows Test Hive"
}

test_hm_colonize_second() {
    capture_cmd bees colonize-hive \
        --name "Second Hive" \
        --path "$REPO/tickets/second_hive"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Colonize second hive" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Colonize second hive"
    pass_test "Colonize second hive"
}

test_hm_list_both() {
    capture_cmd bees list-hives
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "List shows both hives" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "List shows both hives"
    local has_test has_second
    has_test=$(check_json "$CMD_OUT" "'Test Hive' in [h['display_name'] for h in d.get('hives',[])]")
    has_second=$(check_json "$CMD_OUT" "'Second Hive' in [h['display_name'] for h in d.get('hives',[])]")
    if [ "$has_test" != "True" ] || [ "$has_second" != "True" ]; then
        fail_test "List shows both hives" "Missing hive: Test=$has_test, Second=$has_second"
    fi
    pass_test "List shows both hives"
}

test_hm_rename() {
    capture_cmd bees rename-hive --old-name "Test Hive" --new-name "Alpha Hive"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Rename hive" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Rename hive"
    capture_cmd bees list-hives
    local found
    found=$(check_json "$CMD_OUT" "'Alpha Hive' in [h['display_name'] for h in d.get('hives',[])]")
    if [ "$found" != "True" ]; then
        fail_test "Rename hive" "Alpha Hive not found in list after rename"
    fi
    if [ ! -d "$REPO/tickets/alpha_hive" ]; then
        fail_test "Rename hive" "Folder not renamed to alpha_hive on disk"
    fi
    pass_test "Rename hive"
}

test_hm_rename_back() {
    capture_cmd bees rename-hive --old-name "Alpha Hive" --new-name "Test Hive"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Rename hive back" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Rename hive back"
    capture_cmd bees list-hives
    local found
    found=$(check_json "$CMD_OUT" "'Test Hive' in [h['display_name'] for h in d.get('hives',[])]")
    if [ "$found" != "True" ]; then
        fail_test "Rename hive back" "Test Hive not found after rename back"
    fi
    pass_test "Rename hive back"
}

test_hm_rename_no_folder() {
    capture_cmd bees rename-hive --old-name "Test Hive" --new-name "Beta Hive" --no-rename-folder
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Rename --no-rename-folder" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Rename --no-rename-folder"
    capture_cmd bees list-hives
    local found
    found=$(check_json "$CMD_OUT" "'Beta Hive' in [h['display_name'] for h in d.get('hives',[])]")
    if [ "$found" != "True" ]; then
        fail_test "Rename --no-rename-folder" "Beta Hive not found in list"
    fi
    if [ ! -d "$REPO/tickets/test_hive" ]; then
        fail_test "Rename --no-rename-folder" "Folder should still be at test_hive"
    fi
    # Rename back
    capture_cmd bees rename-hive --old-name "Beta Hive" --new-name "Test Hive"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Rename --no-rename-folder" "Rename back failed: $CMD_OUT"
    fi
    pass_test "Rename --no-rename-folder"
}

test_hm_duplicate_name() {
    capture_cmd bees colonize-hive --name "Test Hive" --path "$REPO/tickets/test_hive_dupe"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Duplicate hive name rejected" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "Duplicate hive name rejected"
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    if [ "$error_type" != "duplicate_hive_name" ]; then
        fail_test "Duplicate hive name rejected" "Expected error_type=duplicate_hive_name, got $error_type"
    fi
    pass_test "Duplicate hive name rejected"
}

run_test test_hm_colonize_with_tiers
run_test test_hm_list_one
run_test test_hm_colonize_second
run_test test_hm_list_both
run_test test_hm_rename
run_test test_hm_rename_back
run_test test_hm_rename_no_folder
run_test test_hm_duplicate_name

# === PHASE 2 GROUP A: TIER CONFIGURATION ===

TIER_HIVE=""

test_tc_setup() {
    capture_cmd bees colonize-hive \
        --name "Tier Test Hive" \
        --path "$REPO/tickets/tier_test_hive" \
        --child-tiers '{"t1":["Task","Tasks"],"t2":["Subtask","Subtasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Tier config setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Tier config setup"
    TIER_HIVE=$(check_json "$CMD_OUT" "d['normalized_name']")
    pass_test "Tier config setup"
}

test_tc_get_types() {
    capture_cmd bees get-types
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Get types initial" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Get types initial"
    local status
    status=$(check_json "$CMD_OUT" "d['status']")
    if [ "$status" != "success" ]; then
        fail_test "Get types initial" "status=$status"
    fi
    local has_t1
    has_t1=$(check_json "$CMD_OUT" "'t1' in (d['hives'].get('tier_test_hive',{}) or {})")
    if [ "$has_t1" != "True" ]; then
        fail_test "Get types initial" "tier_test_hive missing t1 in hive config"
    fi
    local glob_val
    glob_val=$(check_json "$CMD_OUT" "d['global']")
    if [ "$glob_val" != "None" ]; then
        fail_test "Get types initial" "Expected global=None, got $glob_val"
    fi
    pass_test "Get types initial"
}

test_tc_set_global() {
    capture_cmd bees set-types --scope global --child-tiers '{"t1":["Epic","Epics"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Set global tiers" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Set global tiers"
    pass_test "Set global tiers"
}

test_tc_hive_override() {
    capture_cmd bees set-types --scope hive --hive "Tier Test Hive" \
        --child-tiers '{"t1":["Task","Tasks"],"t2":["Subtask","Subtasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Per-hive tier override" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Per-hive tier override"
    capture_cmd bees get-types
    local hive_t1
    hive_t1=$(check_json "$CMD_OUT" "(d['hives'].get('tier_test_hive') or {}).get('t1',[''])[0]")
    if [ "$hive_t1" != "Task" ]; then
        fail_test "Per-hive tier override" "Expected hive t1=Task, got $hive_t1"
    fi
    pass_test "Per-hive tier override"
}

test_tc_unset_hive() {
    capture_cmd bees set-types --scope hive --hive "Tier Test Hive" --unset
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Unset hive tiers" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Unset hive tiers"
    capture_cmd bees get-types
    local hive_val
    hive_val=$(check_json "$CMD_OUT" "d['hives'].get('tier_test_hive')")
    if [ "$hive_val" != "None" ]; then
        fail_test "Unset hive tiers" "Expected hive tiers=None after unset, got $hive_val"
    fi
    local glob_t1
    glob_t1=$(check_json "$CMD_OUT" "(d['global'] or {}).get('t1',[''])[0]")
    if [ "$glob_t1" != "Epic" ]; then
        fail_test "Unset hive tiers" "Expected global t1=Epic, got $glob_t1"
    fi
    pass_test "Unset hive tiers"
}

test_tc_restore_unset_global() {
    capture_cmd bees set-types --scope hive --hive "Tier Test Hive" \
        --child-tiers '{"t1":["Task","Tasks"],"t2":["Subtask","Subtasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Restore and unset global" "Restore hive tiers failed: $CMD_OUT"
    fi
    capture_cmd bees set-types --scope global --unset
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Restore and unset global" "Unset global failed: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Restore and unset global"
    pass_test "Restore and unset global"
}

run_test test_tc_setup
run_test test_tc_get_types
run_test test_tc_set_global
run_test test_tc_hive_override
run_test test_tc_unset_hive
run_test test_tc_restore_unset_global

# === PHASE 2 GROUP A: TICKET CRUD ===

BEE1=""
BEE2=""
TASK1=""
SUB1=""

test_crud_setup() {
    capture_cmd bees colonize-hive \
        --name "CRUD Hive" \
        --path "$REPO/tickets/crud_hive" \
        --child-tiers '{"t1":["Task","Tasks"],"t2":["Subtask","Subtasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "CRUD setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "CRUD setup"
    pass_test "CRUD setup"
}

test_crud_create_bee1() {
    capture_cmd bees create-ticket --ticket-type bee --title "First Bee" --hive crud_hive \
        --description "A test bee" --status larva
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Create bee" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Create bee"
    BEE1=$(check_json "$CMD_OUT" "d['ticket_id']")
    if [[ ! "$BEE1" == b.* ]]; then
        fail_test "Create bee" "ticket_id does not start with b.: $BEE1"
    fi
    pass_test "Create bee"
}

test_crud_create_bee2() {
    capture_cmd bees create-ticket --ticket-type bee --title "Second Bee" --hive crud_hive \
        --status pupa
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Create second bee" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Create second bee"
    BEE2=$(check_json "$CMD_OUT" "d['ticket_id']")
    pass_test "Create second bee"
}

test_crud_create_task() {
    capture_cmd bees create-ticket --ticket-type t1 --title "First Task" --hive crud_hive \
        --parent "$BEE1"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Create task" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Create task"
    TASK1=$(check_json "$CMD_OUT" "d['ticket_id']")
    if [[ ! "$TASK1" == t1.* ]]; then
        fail_test "Create task" "ticket_id does not start with t1.: $TASK1"
    fi
    pass_test "Create task"
}

test_crud_create_subtask() {
    capture_cmd bees create-ticket --ticket-type t2 --title "First Subtask" --hive crud_hive \
        --parent "$TASK1"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Create subtask" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Create subtask"
    SUB1=$(check_json "$CMD_OUT" "d['ticket_id']")
    if [[ ! "$SUB1" == t2.* ]]; then
        fail_test "Create subtask" "ticket_id does not start with t2.: $SUB1"
    fi
    pass_test "Create subtask"
}

test_crud_show_single() {
    capture_cmd bees show-ticket --ids "$BEE1"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Show single ticket" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Show single ticket"
    local title status desc children_has_task
    title=$(check_json "$CMD_OUT" "d['tickets'][0]['title']")
    status=$(check_json "$CMD_OUT" "d['tickets'][0]['ticket_status']")
    desc=$(check_json "$CMD_OUT" "d['tickets'][0]['description']")
    children_has_task=$(check_json "$CMD_OUT" "'$TASK1' in (d['tickets'][0].get('children') or [])")
    if [ "$title" != "First Bee" ]; then
        fail_test "Show single ticket" "Expected title=First Bee, got $title"
    fi
    if [ "$status" != "larva" ]; then
        fail_test "Show single ticket" "Expected status=larva, got $status"
    fi
    if [ "$desc" != "A test bee" ]; then
        fail_test "Show single ticket" "Expected description=A test bee, got $desc"
    fi
    if [ "$children_has_task" != "True" ]; then
        fail_test "Show single ticket" "Children should contain $TASK1"
    fi
    pass_test "Show single ticket"
}

test_crud_show_bulk() {
    capture_cmd bees show-ticket --ids "$BEE1" "$BEE2" "$TASK1"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Show bulk tickets" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Show bulk tickets"
    local count nf_count
    count=$(check_json "$CMD_OUT" "len(d['tickets'])")
    nf_count=$(check_json "$CMD_OUT" "len(d.get('not_found',[]))")
    if [ "$count" != "3" ]; then
        fail_test "Show bulk tickets" "Expected 3 tickets, got $count"
    fi
    if [ "$nf_count" != "0" ]; then
        fail_test "Show bulk tickets" "Expected 0 not_found, got $nf_count"
    fi
    pass_test "Show bulk tickets"
}

test_crud_update_title() {
    capture_cmd bees update-ticket --ticket-id "$BEE1" --title "Renamed Bee"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Update title" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Update title"
    capture_cmd bees show-ticket --ids "$BEE1"
    local title
    title=$(check_json "$CMD_OUT" "d['tickets'][0]['title']")
    if [ "$title" != "Renamed Bee" ]; then
        fail_test "Update title" "Expected Renamed Bee, got $title"
    fi
    pass_test "Update title"
}

test_crud_update_status() {
    capture_cmd bees update-ticket --ticket-id "$BEE1" --status worker
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Update status" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Update status"
    capture_cmd bees show-ticket --ids "$BEE1"
    local st
    st=$(check_json "$CMD_OUT" "d['tickets'][0]['ticket_status']")
    if [ "$st" != "worker" ]; then
        fail_test "Update status" "Expected worker, got $st"
    fi
    pass_test "Update status"
}

test_crud_update_tags() {
    capture_cmd bees update-ticket --ticket-id "$BEE1" --tags '["urgent","backend"]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Update tags" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Update tags"
    capture_cmd bees show-ticket --ids "$BEE1"
    local has_urgent has_backend
    has_urgent=$(check_json "$CMD_OUT" "'urgent' in (d['tickets'][0].get('tags') or [])")
    has_backend=$(check_json "$CMD_OUT" "'backend' in (d['tickets'][0].get('tags') or [])")
    if [ "$has_urgent" != "True" ] || [ "$has_backend" != "True" ]; then
        fail_test "Update tags" "Tags not set correctly"
    fi
    pass_test "Update tags"
}

test_crud_update_egg() {
    capture_cmd bees update-ticket --ticket-id "$BEE1" --egg '{"priority":1,"estimate":"2h"}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Update egg" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Update egg"
    capture_cmd bees show-ticket --ids "$BEE1"
    local prio
    prio=$(check_json "$CMD_OUT" "d['tickets'][0].get('egg',{}).get('priority','')")
    if [ "$prio" != "1" ]; then
        fail_test "Update egg" "Expected egg.priority=1, got $prio"
    fi
    pass_test "Update egg"
}

test_crud_clear_tags() {
    capture_cmd bees update-ticket --ticket-id "$BEE1" --tags null
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Clear tags" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Clear tags"
    capture_cmd bees show-ticket --ids "$BEE1"
    local tags
    tags=$(check_json "$CMD_OUT" "d['tickets'][0].get('tags')")
    if [ "$tags" != "None" ] && [ "$tags" != "[]" ]; then
        fail_test "Clear tags" "Expected tags=None or [], got $tags"
    fi
    pass_test "Clear tags"
}

test_crud_delete_single() {
    capture_cmd bees create-ticket --ticket-type bee --title "Doomed Bee" --hive crud_hive
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Delete single" "Create failed: $CMD_OUT"
    fi
    local doomed_id
    doomed_id=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees delete-ticket --ids "$doomed_id"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Delete single" "Delete failed: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Delete single"
    capture_cmd bees show-ticket --ids "$doomed_id"
    local nf
    nf=$(check_json "$CMD_OUT" "'$doomed_id' in d.get('not_found',[])")
    if [ "$nf" != "True" ]; then
        fail_test "Delete single" "Deleted ticket still found"
    fi
    pass_test "Delete single"
}

test_crud_delete_bulk() {
    capture_cmd bees create-ticket --ticket-type bee --title "Bulk Doom 1" --hive crud_hive
    local d1
    d1=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type bee --title "Bulk Doom 2" --hive crud_hive
    local d2
    d2=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees delete-ticket --ids "$d1" "$d2"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Delete bulk" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Delete bulk"
    capture_cmd bees show-ticket --ids "$d1" "$d2"
    local nf_count
    nf_count=$(check_json "$CMD_OUT" "len(d.get('not_found',[]))")
    if [ "$nf_count" != "2" ]; then
        fail_test "Delete bulk" "Expected 2 not_found, got $nf_count"
    fi
    pass_test "Delete bulk"
}

test_crud_parent_child_sync() {
    capture_cmd bees show-ticket --ids "$BEE1"
    local bee_has_task
    bee_has_task=$(check_json "$CMD_OUT" "'$TASK1' in (d['tickets'][0].get('children') or [])")
    if [ "$bee_has_task" != "True" ]; then
        fail_test "Parent-child sync" "BEE1 children missing TASK1"
    fi
    capture_cmd bees show-ticket --ids "$TASK1"
    local task_parent task_has_sub
    task_parent=$(check_json "$CMD_OUT" "d['tickets'][0].get('parent','')")
    task_has_sub=$(check_json "$CMD_OUT" "'$SUB1' in (d['tickets'][0].get('children') or [])")
    if [ "$task_parent" != "$BEE1" ]; then
        fail_test "Parent-child sync" "TASK1 parent expected $BEE1, got $task_parent"
    fi
    if [ "$task_has_sub" != "True" ]; then
        fail_test "Parent-child sync" "TASK1 children missing SUB1"
    fi
    capture_cmd bees show-ticket --ids "$SUB1"
    local sub_parent
    sub_parent=$(check_json "$CMD_OUT" "d['tickets'][0].get('parent','')")
    if [ "$sub_parent" != "$TASK1" ]; then
        fail_test "Parent-child sync" "SUB1 parent expected $TASK1, got $sub_parent"
    fi
    pass_test "Parent-child sync"
}

test_crud_reject_parent_change() {
    capture_cmd bees update-ticket --ticket-id "$TASK1" --parent "$BEE2"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Reject parent change" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "Reject parent change"
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    if [ -z "$error_type" ]; then
        fail_test "Reject parent change" "No error_type in response"
    fi
    pass_test "Reject parent change"
}

test_crud_cascading_delete() {
    capture_cmd bees create-ticket --ticket-type bee --title "Cascade Bee" --hive crud_hive
    local cbee
    cbee=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t1 --title "Cascade Task" --hive crud_hive --parent "$cbee"
    local ctask
    ctask=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t2 --title "Cascade Sub" --hive crud_hive --parent "$ctask"
    local csub
    csub=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees delete-ticket --ids "$cbee"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Cascading delete" "Delete failed: $CMD_OUT"
    fi
    capture_cmd bees show-ticket --ids "$cbee" "$ctask" "$csub"
    local nf_count
    nf_count=$(check_json "$CMD_OUT" "len(d.get('not_found',[]))")
    if [ "$nf_count" != "3" ]; then
        fail_test "Cascading delete" "Expected 3 not_found, got $nf_count"
    fi
    pass_test "Cascading delete"
}

test_crud_reject_parent_children_update() {
    capture_cmd bees create-ticket --ticket-type bee --title "Update Reject Bee" --hive crud_hive
    local rj_bee
    rj_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    # --parent on update should fail
    capture_cmd bees update-ticket --ticket-id "$rj_bee" --parent "$BEE1"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Reject parent/children on update" "update --parent should fail"
    fi
    assert_no_traceback "$CMD_OUT" "Reject parent/children on update"
    # --children on update should fail (unrecognized arg)
    capture_cmd bees update-ticket --ticket-id "$rj_bee" --children '["x"]'
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Reject parent/children on update" "update --children should fail"
    fi
    assert_no_traceback "$CMD_OUT" "Reject parent/children on update"
    # Valid update should succeed
    capture_cmd bees update-ticket --ticket-id "$rj_bee" --title "Updated Reject Bee"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Reject parent/children on update" "Valid update failed: $CMD_OUT"
    fi
    pass_test "Reject parent/children on update"
}

test_crud_add_remove_tags() {
    capture_cmd bees update-ticket --ticket-id "$BEE1" --add-tags '["alpha","beta","gamma"]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Add/remove tags" "add-tags failed: $CMD_OUT"
    fi
    capture_cmd bees show-ticket --ids "$BEE1"
    local has_a has_b has_g
    has_a=$(check_json "$CMD_OUT" "'alpha' in (d['tickets'][0].get('tags') or [])")
    has_b=$(check_json "$CMD_OUT" "'beta' in (d['tickets'][0].get('tags') or [])")
    has_g=$(check_json "$CMD_OUT" "'gamma' in (d['tickets'][0].get('tags') or [])")
    if [ "$has_a" != "True" ] || [ "$has_b" != "True" ] || [ "$has_g" != "True" ]; then
        fail_test "Add/remove tags" "Expected alpha,beta,gamma after add-tags"
    fi
    capture_cmd bees update-ticket --ticket-id "$BEE1" --remove-tags '["beta"]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Add/remove tags" "remove-tags failed: $CMD_OUT"
    fi
    capture_cmd bees show-ticket --ids "$BEE1"
    has_a=$(check_json "$CMD_OUT" "'alpha' in (d['tickets'][0].get('tags') or [])")
    has_b=$(check_json "$CMD_OUT" "'beta' in (d['tickets'][0].get('tags') or [])")
    has_g=$(check_json "$CMD_OUT" "'gamma' in (d['tickets'][0].get('tags') or [])")
    if [ "$has_a" != "True" ] || [ "$has_b" != "False" ] || [ "$has_g" != "True" ]; then
        fail_test "Add/remove tags" "Expected alpha,gamma without beta after remove-tags"
    fi
    pass_test "Add/remove tags"
}

run_test test_crud_setup
run_test test_crud_create_bee1
run_test test_crud_create_bee2
run_test test_crud_create_task
run_test test_crud_create_subtask
run_test test_crud_show_single
run_test test_crud_show_bulk
run_test test_crud_update_title
run_test test_crud_update_status
run_test test_crud_update_tags
run_test test_crud_update_egg
run_test test_crud_clear_tags
run_test test_crud_delete_single
run_test test_crud_delete_bulk
run_test test_crud_parent_child_sync
run_test test_crud_reject_parent_change
run_test test_crud_cascading_delete
run_test test_crud_reject_parent_children_update
run_test test_crud_add_remove_tags

# === PHASE 2 GROUP B: DEPENDENCIES ===

DEP_A=""
DEP_B=""
DEP_C=""
DANG_A=""

test_dep_setup() {
    capture_cmd bees colonize-hive \
        --name "Dep Hive" \
        --path "$REPO/tickets/dep_hive" \
        --child-tiers '{"t1":["Task","Tasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Dep setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Dep setup"
    pass_test "Dep setup"
}

test_dep_create_with_up_deps() {
    capture_cmd bees create-ticket --ticket-type bee --title "Dep A" --hive dep_hive
    DEP_A=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type bee --title "Dep B" --hive dep_hive \
        --up-deps "[\"$DEP_A\"]"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Create with up-deps" "exit $CMD_EXIT: $CMD_OUT"
    fi
    DEP_B=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees show-ticket --ids "$DEP_B"
    local has_dep
    has_dep=$(check_json "$CMD_OUT" "'$DEP_A' in (d['tickets'][0].get('up_dependencies') or [])")
    if [ "$has_dep" != "True" ]; then
        fail_test "Create with up-deps" "DEP_B up_dependencies missing DEP_A"
    fi
    pass_test "Create with up-deps"
}

test_dep_bidirectional_sync() {
    capture_cmd bees show-ticket --ids "$DEP_A"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Bidirectional dep sync" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_down
    has_down=$(check_json "$CMD_OUT" "'$DEP_B' in (d['tickets'][0].get('down_dependencies') or [])")
    if [ "$has_down" != "True" ]; then
        fail_test "Bidirectional dep sync" "DEP_A down_dependencies missing DEP_B"
    fi
    pass_test "Bidirectional dep sync"
}

test_dep_update() {
    capture_cmd bees create-ticket --ticket-type bee --title "Dep C" --hive dep_hive
    DEP_C=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees update-ticket --ticket-id "$DEP_B" --up-deps "[\"$DEP_A\",\"$DEP_C\"]"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Update deps" "exit $CMD_EXIT: $CMD_OUT"
    fi
    capture_cmd bees show-ticket --ids "$DEP_C"
    local has_down
    has_down=$(check_json "$CMD_OUT" "'$DEP_B' in (d['tickets'][0].get('down_dependencies') or [])")
    if [ "$has_down" != "True" ]; then
        fail_test "Update deps" "DEP_C down_dependencies missing DEP_B"
    fi
    pass_test "Update deps"
}

test_dep_delete_with_cleanup() {
    # Enable delete_with_dependencies in global config
    python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.bees' / 'config.json'
d = json.loads(p.read_text())
d['delete_with_dependencies'] = True
p.write_text(json.dumps(d))
"
    capture_cmd bees delete-ticket --ids "$DEP_B"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Delete with dep cleanup" "Delete failed: $CMD_OUT"
    fi
    # Check DEP_A no longer references DEP_B
    capture_cmd bees show-ticket --ids "$DEP_A"
    local a_has_b
    a_has_b=$(check_json "$CMD_OUT" "'$DEP_B' in (d['tickets'][0].get('down_dependencies') or [])")
    if [ "$a_has_b" != "False" ]; then
        fail_test "Delete with dep cleanup" "DEP_A still references deleted DEP_B"
    fi
    # Check DEP_C no longer references DEP_B
    capture_cmd bees show-ticket --ids "$DEP_C"
    local c_has_b
    c_has_b=$(check_json "$CMD_OUT" "'$DEP_B' in (d['tickets'][0].get('down_dependencies') or [])")
    if [ "$c_has_b" != "False" ]; then
        fail_test "Delete with dep cleanup" "DEP_C still references deleted DEP_B"
    fi
    # Remove delete_with_dependencies from config
    python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.bees' / 'config.json'
d = json.loads(p.read_text())
d.pop('delete_with_dependencies', None)
p.write_text(json.dumps(d))
"
    pass_test "Delete with dep cleanup"
}

test_dep_default_dangling() {
    capture_cmd bees create-ticket --ticket-type bee --title "Dang A" --hive dep_hive
    DANG_A=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type bee --title "Dang B" --hive dep_hive \
        --up-deps "[\"$DANG_A\"]"
    local dang_b
    dang_b=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees delete-ticket --ids "$dang_b"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Default dangling refs" "Delete failed: $CMD_OUT"
    fi
    # DANG_A should still have dangling ref to deleted dang_b
    capture_cmd bees show-ticket --ids "$DANG_A"
    local has_dangling
    has_dangling=$(check_json "$CMD_OUT" "'$dang_b' in (d['tickets'][0].get('down_dependencies') or [])")
    if [ "$has_dangling" != "True" ]; then
        fail_test "Default dangling refs" "DANG_A should still reference deleted ticket (dangling)"
    fi
    pass_test "Default dangling refs"
}

test_dep_bulk_delete_ordering() {
    capture_cmd bees create-ticket --ticket-type bee --title "Bulk Bee" --hive dep_hive
    local bulk_bee
    bulk_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t1 --title "Bulk Task" --hive dep_hive --parent "$bulk_bee"
    local bulk_task
    bulk_task=$(check_json "$CMD_OUT" "d['ticket_id']")
    # Pass child first, then parent — bees should be processed first
    capture_cmd bees delete-ticket --ids "$bulk_task" "$bulk_bee"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Bulk delete ordering" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_deleted has_not_found has_failed
    has_deleted=$(check_json "$CMD_OUT" "'deleted' in d")
    has_not_found=$(check_json "$CMD_OUT" "'not_found' in d")
    has_failed=$(check_json "$CMD_OUT" "'failed' in d")
    if [ "$has_deleted" != "True" ] || [ "$has_not_found" != "True" ] || [ "$has_failed" != "True" ]; then
        fail_test "Bulk delete ordering" "Response missing deleted/not_found/failed keys"
    fi
    # Bee should be in deleted, task in not_found (already removed by rmtree)
    local bee_deleted task_nf
    bee_deleted=$(check_json "$CMD_OUT" "'$bulk_bee' in d.get('deleted',[])")
    task_nf=$(check_json "$CMD_OUT" "'$bulk_task' in d.get('not_found',[])")
    if [ "$bee_deleted" != "True" ]; then
        fail_test "Bulk delete ordering" "Bee not in deleted list"
    fi
    if [ "$task_nf" != "True" ]; then
        fail_test "Bulk delete ordering" "Task not in not_found list"
    fi
    pass_test "Bulk delete ordering"
}

test_dep_clean_deps_flag_rejected() {
    capture_cmd bees delete-ticket --ids "$DANG_A" --clean-dependencies
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "clean-dependencies rejected" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "clean-dependencies rejected"
    pass_test "clean-dependencies rejected"
}

run_test test_dep_setup
run_test test_dep_create_with_up_deps
run_test test_dep_bidirectional_sync
run_test test_dep_update
run_test test_dep_delete_with_cleanup
run_test test_dep_default_dangling
run_test test_dep_bulk_delete_ordering
run_test test_dep_clean_deps_flag_rejected

# === PHASE 2 GROUP B: ID AND GUID VALIDATION ===

ID_BEE=""
ID_TASK=""
ID_SUB=""

test_id_setup() {
    capture_cmd bees colonize-hive \
        --name "ID Test Hive" \
        --path "$REPO/tickets/id_test_hive" \
        --child-tiers '{"t1":["Task","Tasks"],"t2":["Subtask","Subtasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "ID setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    capture_cmd bees create-ticket --ticket-type bee --title "ID Bee" --hive id_test_hive
    ID_BEE=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t1 --title "ID Task" --hive id_test_hive --parent "$ID_BEE"
    ID_TASK=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t2 --title "ID Subtask" --hive id_test_hive --parent "$ID_TASK"
    ID_SUB=$(check_json "$CMD_OUT" "d['ticket_id']")
    pass_test "ID setup"
}

test_id_valid_ids() {
    capture_cmd bees show-ticket --ids "$ID_BEE" "$ID_TASK" "$ID_SUB"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Valid IDs accepted" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local count nf
    count=$(check_json "$CMD_OUT" "len(d['tickets'])")
    nf=$(check_json "$CMD_OUT" "len(d.get('not_found',[]))")
    if [ "$count" != "3" ] || [ "$nf" != "0" ]; then
        fail_test "Valid IDs accepted" "Expected 3 tickets, 0 not_found; got $count tickets, $nf not_found"
    fi
    pass_test "Valid IDs accepted"
}

test_id_bee_length() {
    local suffix="${ID_BEE#b.}"
    local len=${#suffix}
    if [ "$len" -ne 3 ]; then
        fail_test "Bee ID is 3 chars" "Expected 3 chars after b., got $len ($ID_BEE)"
    fi
    pass_test "Bee ID is 3 chars"
}

test_id_task_length() {
    # t1 format: t1.<bee_id>.<suffix> e.g. t1.abc.de → 3+1+2 = 6 chars after t1.
    local suffix="${ID_TASK#t1.}"
    local len=${#suffix}
    if [ "$len" -ne 6 ]; then
        fail_test "Task ID is 6 chars" "Expected 6 chars after t1., got $len ($ID_TASK)"
    fi
    pass_test "Task ID is 6 chars"
}

test_id_subtask_length() {
    # t2 format: t2.<bee_id>.<task_sfx>.<suffix> e.g. t2.abc.de.fg → 3+1+2+1+2 = 9 chars after t2.
    local suffix="${ID_SUB#t2.}"
    local len=${#suffix}
    if [ "$len" -ne 9 ]; then
        fail_test "Subtask ID is 9 chars" "Expected 9 chars after t2., got $len ($ID_SUB)"
    fi
    pass_test "Subtask ID is 9 chars"
}

test_id_charset() {
    # Check only the auto-generated suffix segment (last segment after last dot)
    local valid_re='^[123456789abcdefghijkmnopqrstuvwxyz]+$'
    local bee_sfx="${ID_BEE##*.}"
    local task_sfx="${ID_TASK##*.}"
    local sub_sfx="${ID_SUB##*.}"
    if ! echo "$bee_sfx" | grep -qE "$valid_re"; then
        fail_test "ID charset valid" "Bee suffix '$bee_sfx' contains invalid chars"
    fi
    if ! echo "$task_sfx" | grep -qE "$valid_re"; then
        fail_test "ID charset valid" "Task suffix '$task_sfx' contains invalid chars"
    fi
    if ! echo "$sub_sfx" | grep -qE "$valid_re"; then
        fail_test "ID charset valid" "Subtask suffix '$sub_sfx' contains invalid chars"
    fi
    pass_test "ID charset valid"
}

test_id_path_traversal() {
    capture_cmd bees show-ticket --ids "b.../../etc"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Path traversal rejected" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "Path traversal rejected"
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')" 2>/dev/null || echo "")
    # Accept any error (might be invalid_ticket_id or parse error)
    pass_test "Path traversal rejected"
}

test_id_guid_length() {
    capture_cmd bees show-ticket --ids "$ID_BEE"
    local guid
    guid=$(check_json "$CMD_OUT" "d['tickets'][0]['guid']")
    local len=${#guid}
    if [ "$len" -ne 32 ]; then
        fail_test "GUID is 32 chars" "Expected 32 chars, got $len ($guid)"
    fi
    pass_test "GUID is 32 chars"
}

test_id_guid_charset() {
    capture_cmd bees show-ticket --ids "$ID_BEE"
    local guid
    guid=$(check_json "$CMD_OUT" "d['tickets'][0]['guid']")
    local valid_re='^[123456789abcdefghijkmnopqrstuvwxyz]+$'
    if ! echo "$guid" | grep -qE "$valid_re"; then
        fail_test "GUID charset valid" "GUID '$guid' contains invalid chars"
    fi
    pass_test "GUID charset valid"
}

test_id_guid_prefix() {
    capture_cmd bees show-ticket --ids "$ID_BEE"
    local guid
    guid=$(check_json "$CMD_OUT" "d['tickets'][0]['guid']")
    local bee_suffix="${ID_BEE#b.}"
    local guid_prefix="${guid:0:${#bee_suffix}}"
    if [ "$guid_prefix" != "$bee_suffix" ]; then
        fail_test "GUID prefix matches short_id" "Expected GUID to start with '$bee_suffix', got '$guid_prefix'"
    fi
    pass_test "GUID prefix matches short_id"
}

run_test test_id_setup
run_test test_id_valid_ids
run_test test_id_bee_length
run_test test_id_task_length
run_test test_id_subtask_length
run_test test_id_charset
run_test test_id_path_traversal
run_test test_id_guid_length
run_test test_id_guid_charset
run_test test_id_guid_prefix

# === PHASE 2 GROUP B: STATUS BEHAVIOR ===

STATUS_BEE=""

test_status_setup() {
    capture_cmd bees colonize-hive \
        --name "Status Hive" \
        --path "$REPO/tickets/status_hive"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Status setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    pass_test "Status setup"
}

test_status_freeform() {
    capture_cmd bees create-ticket --ticket-type bee --title "Status Test Bee" --hive status_hive
    STATUS_BEE=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees update-ticket --ticket-id "$STATUS_BEE" --status "any_custom_status"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Freeform status accepted" "exit $CMD_EXIT: $CMD_OUT"
    fi
    capture_cmd bees show-ticket --ids "$STATUS_BEE"
    local st
    st=$(check_json "$CMD_OUT" "d['tickets'][0]['ticket_status']")
    if [ "$st" != "any_custom_status" ]; then
        fail_test "Freeform status accepted" "Expected any_custom_status, got $st"
    fi
    pass_test "Freeform status accepted"
}

test_status_linter_flags_invalid() {
    # Configure status_values for the hive
    capture_cmd bees set-status-values --scope hive --hive "Status Hive" \
        --status-values '["larva","pupa","worker","finished"]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Linter flags invalid status" "set-status-values failed: $CMD_OUT"
    fi
    # Edit the bee's frontmatter directly to set bogus status
    local ticket_file
    ticket_file=$(find "$REPO/tickets/status_hive" -name "*.md" ! -path '*/.hive/*' ! -path '*/cemetery/*' | head -1)
    if [ -z "$ticket_file" ]; then
        fail_test "Linter flags invalid status" "Could not find ticket file"
    fi
    python3 -c "
import re, pathlib
f = pathlib.Path('$ticket_file')
t = f.read_text()
t = re.sub(r'ticket_status: .*', 'ticket_status: bogus', t)
f.write_text(t)
"
    # Run sanitizer
    capture_cmd bees sanitize-hive --hive "Status Hive"
    assert_no_traceback "$CMD_OUT" "Linter flags invalid status"
    # Check that errors_remaining mentions invalid status
    local has_errors
    has_errors=$(check_json "$CMD_OUT" "len(d.get('errors_remaining',[])) > 0")
    if [ "$has_errors" != "True" ]; then
        fail_test "Linter flags invalid status" "Expected errors_remaining for bogus status"
    fi
    pass_test "Linter flags invalid status"
}

run_test test_status_setup
run_test test_status_freeform
run_test test_status_linter_flags_invalid

# === PHASE 2 GROUP B: FREEFORM QUERIES ===

QB1=""
QB2=""
QTASK1=""
QB3=""
QA=""
QB=""

test_query_setup() {
    # Create hive A with t1 tiers
    capture_cmd bees colonize-hive \
        --name "Query Hive A" \
        --path "$REPO/tickets/query_hive_a" \
        --child-tiers '{"t1":["Task","Tasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Query setup" "Colonize hive A failed: $CMD_OUT"
    fi
    # Create hive B with no tiers
    capture_cmd bees colonize-hive \
        --name "Query Hive B" \
        --path "$REPO/tickets/query_hive_b"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Query setup" "Colonize hive B failed: $CMD_OUT"
    fi
    # Worker Bee in A
    capture_cmd bees create-ticket --ticket-type bee --title "Worker Bee" --hive query_hive_a --status worker
    QB1=$(check_json "$CMD_OUT" "d['ticket_id']")
    # Pupa Bee in A with tag
    capture_cmd bees create-ticket --ticket-type bee --title "Pupa Bee" --hive query_hive_a \
        --status pupa --tags '["searchable"]'
    QB2=$(check_json "$CMD_OUT" "d['ticket_id']")
    # Task under Worker Bee
    capture_cmd bees create-ticket --ticket-type t1 --title "Query Task" --hive query_hive_a --parent "$QB1"
    QTASK1=$(check_json "$CMD_OUT" "d['ticket_id']")
    # Dependency pair: QA → QB
    capture_cmd bees create-ticket --ticket-type bee --title "Dep Source" --hive query_hive_a
    QA=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type bee --title "Dep Target" --hive query_hive_a \
        --up-deps "[\"$QA\"]"
    QB=$(check_json "$CMD_OUT" "d['ticket_id']")
    # Bee in hive B
    capture_cmd bees create-ticket --ticket-type bee --title "Other Hive Bee" --hive query_hive_b
    QB3=$(check_json "$CMD_OUT" "d['ticket_id']")
    pass_test "Query setup"
}

test_query_type_bee() {
    capture_cmd bees execute-freeform-query --query-yaml "- [type=bee, hive=query_hive_a]"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Query by type=bee" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local all_bees
    all_bees=$(check_json "$CMD_OUT" "all(tid.startswith('b.') for tid in d.get('ticket_ids',[]))")
    if [ "$all_bees" != "True" ]; then
        fail_test "Query by type=bee" "Not all results are bees"
    fi
    pass_test "Query by type=bee"
}

test_query_type_t1() {
    capture_cmd bees execute-freeform-query --query-yaml "- [type=t1, hive=query_hive_a]"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Query by type=t1" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local all_tasks
    all_tasks=$(check_json "$CMD_OUT" "all(tid.startswith('t1.') for tid in d.get('ticket_ids',[]))")
    if [ "$all_tasks" != "True" ]; then
        fail_test "Query by type=t1" "Not all results are t1 tasks"
    fi
    pass_test "Query by type=t1"
}

test_query_by_status() {
    capture_cmd bees execute-freeform-query --query-yaml "- [status=worker]"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Query by status" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_qb1
    has_qb1=$(check_json "$CMD_OUT" "'$QB1' in d.get('ticket_ids',[])")
    if [ "$has_qb1" != "True" ]; then
        fail_test "Query by status" "Worker Bee ($QB1) not found in status=worker results"
    fi
    pass_test "Query by status"
}

test_query_by_title() {
    capture_cmd bees execute-freeform-query --query-yaml "- [title~Worker]"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Query by title" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_qb1
    has_qb1=$(check_json "$CMD_OUT" "'$QB1' in d.get('ticket_ids',[])")
    if [ "$has_qb1" != "True" ]; then
        fail_test "Query by title" "Worker Bee not found in title~Worker results"
    fi
    pass_test "Query by title"
}

test_query_by_tag() {
    capture_cmd bees execute-freeform-query --query-yaml "- [tag~searchable]"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Query by tag" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_qb2
    has_qb2=$(check_json "$CMD_OUT" "'$QB2' in d.get('ticket_ids',[])")
    if [ "$has_qb2" != "True" ]; then
        fail_test "Query by tag" "Pupa Bee ($QB2) not found in tag~searchable results"
    fi
    pass_test "Query by tag"
}

test_query_graph_children() {
    capture_cmd bees execute-freeform-query \
        --query-yaml $'- [type=bee, hive=query_hive_a]\n- [children]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Query children traversal" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_task
    has_task=$(check_json "$CMD_OUT" "'$QTASK1' in d.get('ticket_ids',[])")
    if [ "$has_task" != "True" ]; then
        fail_test "Query children traversal" "QTASK1 not found in children results"
    fi
    pass_test "Query children traversal"
}

test_query_graph_parent() {
    capture_cmd bees execute-freeform-query \
        --query-yaml $'- [type=t1, hive=query_hive_a]\n- [parent]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Query parent traversal" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local all_bees
    all_bees=$(check_json "$CMD_OUT" "all(tid.startswith('b.') for tid in d.get('ticket_ids',[]))")
    if [ "$all_bees" != "True" ]; then
        fail_test "Query parent traversal" "Parent results should be bees"
    fi
    pass_test "Query parent traversal"
}

test_query_hive_filter() {
    capture_cmd bees execute-freeform-query --query-yaml "- [hive=query_hive_a, type=bee]"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Query hive filter" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_qb3
    has_qb3=$(check_json "$CMD_OUT" "'$QB3' in d.get('ticket_ids',[])")
    if [ "$has_qb3" != "False" ]; then
        fail_test "Query hive filter" "Hive B ticket found in hive A query"
    fi
    pass_test "Query hive filter"
}

test_query_up_deps() {
    capture_cmd bees execute-freeform-query \
        --query-yaml $'- [type=bee]\n- [up_dependencies]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Query up_dependencies" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_qa
    has_qa=$(check_json "$CMD_OUT" "'$QA' in d.get('ticket_ids',[])")
    if [ "$has_qa" != "True" ]; then
        fail_test "Query up_dependencies" "QA not found in up_dependencies traversal"
    fi
    pass_test "Query up_dependencies"
}

test_query_down_deps() {
    capture_cmd bees execute-freeform-query \
        --query-yaml $'- [type=bee]\n- [down_dependencies]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Query down_dependencies" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_qb
    has_qb=$(check_json "$CMD_OUT" "'$QB' in d.get('ticket_ids',[])")
    if [ "$has_qb" != "True" ]; then
        fail_test "Query down_dependencies" "QB not found in down_dependencies traversal"
    fi
    pass_test "Query down_dependencies"
}

run_test test_query_setup
run_test test_query_type_bee
run_test test_query_type_t1
run_test test_query_by_status
run_test test_query_by_title
run_test test_query_by_tag
run_test test_query_graph_children
run_test test_query_graph_parent
run_test test_query_hive_filter
run_test test_query_up_deps
run_test test_query_down_deps

# === PHASE 2 GROUP B: NAMED QUERIES ===

NQ_BEE=""

test_nq_setup() {
    capture_cmd bees colonize-hive \
        --name "NQ Hive" \
        --path "$REPO/tickets/nq_hive"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "NQ setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    capture_cmd bees create-ticket --ticket-type bee --title "NQ Worker Bee" --hive nq_hive --status worker
    NQ_BEE=$(check_json "$CMD_OUT" "d['ticket_id']")
    pass_test "NQ setup"
}

test_nq_add_global() {
    capture_cmd bees add-named-query --query-name "all_bees" --query-yaml "- [type=bee]" --scope global
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Add global named query" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Add global named query"
    pass_test "Add global named query"
}

test_nq_execute() {
    capture_cmd bees execute-named-query --query-name "all_bees"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Execute named query" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local count
    count=$(check_json "$CMD_OUT" "d.get('result_count',0)")
    if [ "$count" -lt 1 ]; then
        fail_test "Execute named query" "Expected at least 1 result, got $count"
    fi
    pass_test "Execute named query"
}

test_nq_list() {
    capture_cmd bees list-named-queries
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "List named queries" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_all_bees
    has_all_bees=$(check_json "$CMD_OUT" "'all_bees' in [q['name'] for q in d.get('queries',[])]")
    if [ "$has_all_bees" != "True" ]; then
        fail_test "List named queries" "all_bees not found in query list"
    fi
    pass_test "List named queries"
}

test_nq_conflict() {
    capture_cmd bees add-named-query --query-name "all_bees" --query-yaml "- [type=bee]" --scope repo
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Reject conflicting query name" "Expected failure but got success"
    fi
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    if [ "$error_type" != "query_name_conflict" ]; then
        fail_test "Reject conflicting query name" "Expected error_type=query_name_conflict, got $error_type"
    fi
    pass_test "Reject conflicting query name"
}

test_nq_add_repo() {
    capture_cmd bees add-named-query --query-name "worker_bees" \
        --query-yaml "- [type=bee, status=worker]" --scope repo
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Add repo-scoped query" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Add repo-scoped query"
    pass_test "Add repo-scoped query"
}

test_nq_execute_repo() {
    capture_cmd bees execute-named-query --query-name "worker_bees"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Execute repo-scoped query" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local count
    count=$(check_json "$CMD_OUT" "d.get('result_count',0)")
    if [ "$count" -lt 1 ]; then
        fail_test "Execute repo-scoped query" "Expected at least 1 result, got $count"
    fi
    pass_test "Execute repo-scoped query"
}

test_nq_delete_repo() {
    capture_cmd bees delete-named-query --query-name "worker_bees"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Delete repo-scoped query" "exit $CMD_EXIT: $CMD_OUT"
    fi
    # Execute should now fail
    capture_cmd bees execute-named-query --query-name "worker_bees"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Delete repo-scoped query" "Query still executes after deletion"
    fi
    pass_test "Delete repo-scoped query"
}

test_nq_delete_global() {
    capture_cmd bees delete-named-query --query-name "all_bees"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Delete global query" "exit $CMD_EXIT: $CMD_OUT"
    fi
    capture_cmd bees execute-named-query --query-name "all_bees"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Delete global query" "Query still executes after deletion"
    fi
    pass_test "Delete global query"
}

run_test test_nq_setup
run_test test_nq_add_global
run_test test_nq_execute
run_test test_nq_list
run_test test_nq_conflict
run_test test_nq_add_repo
run_test test_nq_execute_repo
run_test test_nq_delete_repo
run_test test_nq_delete_global

# === FORMER PHASE 5 GROUP A: EGG RESOLVER ===

EGG_BEE1=""
EGG_BEE2=""
EGG_BEE3=""

test_egg_setup() {
    capture_cmd bees colonize-hive \
        --name "Egg Hive" \
        --path "$REPO/tickets/egg_hive"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Egg setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Egg setup"
    pass_test "Egg setup"
}

test_egg_string_inline() {
    capture_cmd bees create-ticket --ticket-type bee --title "String Egg Bee" \
        --hive egg_hive --egg '"hello"'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "String egg inline" "Create failed: $CMD_OUT"
    fi
    EGG_BEE1=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees show-ticket --ids "$EGG_BEE1"
    local egg_val
    egg_val=$(check_json "$CMD_OUT" "d['tickets'][0]['egg']")
    if [ "$egg_val" != "hello" ]; then
        fail_test "String egg inline" "Expected egg='hello', got '$egg_val'"
    fi
    pass_test "String egg inline"
}

test_egg_null_inline() {
    capture_cmd bees create-ticket --ticket-type bee --title "Null Egg Bee" \
        --hive egg_hive --egg 'null'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Null egg inline" "Create failed: $CMD_OUT"
    fi
    EGG_BEE2=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees show-ticket --ids "$EGG_BEE2"
    local egg_val
    egg_val=$(check_json "$CMD_OUT" "d['tickets'][0]['egg']")
    if [ "$egg_val" != "None" ]; then
        fail_test "Null egg inline" "Expected egg=None, got '$egg_val'"
    fi
    pass_test "Null egg inline"
}

test_egg_object_inline() {
    capture_cmd bees create-ticket --ticket-type bee --title "Object Egg Bee" \
        --hive egg_hive --egg '{"key":"val"}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Object egg inline" "Create failed: $CMD_OUT"
    fi
    EGG_BEE3=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees show-ticket --ids "$EGG_BEE3"
    local egg_key
    egg_key=$(check_json "$CMD_OUT" "d['tickets'][0]['egg'].get('key','')")
    if [ "$egg_key" != "val" ]; then
        fail_test "Object egg inline" "Expected egg.key='val', got '$egg_key'"
    fi
    pass_test "Object egg inline"
}

test_egg_custom_resolver() {
    # Create a shell script resolver that outputs JSON
    mkdir -p "$REPO/scripts"
    cat > "$REPO/scripts/egg_resolver.sh" << 'RESOLVER'
#!/bin/bash
# Parse --egg-value argument
EGG_VALUE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --egg-value) EGG_VALUE="$2"; shift 2 ;;
        --repo-root) shift 2 ;;
        *) shift ;;
    esac
done
echo "{\"resolved\": true, \"original\": \"$EGG_VALUE\"}"
RESOLVER
    chmod +x "$REPO/scripts/egg_resolver.sh"
    capture_cmd bees colonize-hive \
        --name "Resolver Hive" \
        --path "$REPO/tickets/resolver_hive" \
        --egg-resolver "$REPO/scripts/egg_resolver.sh"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Custom egg resolver" "Colonize failed: $CMD_OUT"
    fi
    capture_cmd bees create-ticket --ticket-type bee --title "Resolved Bee" \
        --hive resolver_hive --egg '"test_value"'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Custom egg resolver" "Create failed: $CMD_OUT"
    fi
    local res_bee
    res_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees show-ticket --ids "$res_bee"
    local resolved
    resolved=$(check_json "$CMD_OUT" "d['tickets'][0]['egg'].get('resolved', False)")
    if [ "$resolved" != "True" ]; then
        fail_test "Custom egg resolver" "Expected resolved=True in egg output"
    fi
    pass_test "Custom egg resolver"
}

test_egg_resolver_timeout() {
    # Create a script that sleeps forever
    cat > "$REPO/scripts/slow_resolver.sh" << 'RESOLVER'
#!/bin/bash
sleep 60
echo '{"never":"reached"}'
RESOLVER
    chmod +x "$REPO/scripts/slow_resolver.sh"
    capture_cmd bees colonize-hive \
        --name "Timeout Hive" \
        --path "$REPO/tickets/timeout_hive" \
        --egg-resolver "$REPO/scripts/slow_resolver.sh" \
        --egg-resolver-timeout 2
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Egg resolver timeout" "Colonize failed: $CMD_OUT"
    fi
    capture_cmd bees create-ticket --ticket-type bee --title "Timeout Bee" \
        --hive timeout_hive --egg '"test"'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Egg resolver timeout" "Create failed: $CMD_OUT"
    fi
    local to_bee
    to_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    # Show should succeed but egg resolution should fail gracefully
    capture_cmd bees show-ticket --ids "$to_bee"
    assert_no_traceback "$CMD_OUT" "Egg resolver timeout"
    # The ticket should still be returned (with errors or fallback egg)
    local ticket_count
    ticket_count=$(check_json "$CMD_OUT" "len(d.get('tickets',[]))")
    if [ "$ticket_count" != "1" ]; then
        fail_test "Egg resolver timeout" "Expected 1 ticket returned, got $ticket_count"
    fi
    # Check that errors list mentions the timeout
    local has_errors
    has_errors=$(check_json "$CMD_OUT" "len(d.get('errors',[])) > 0")
    if [ "$has_errors" != "True" ]; then
        fail_test "Egg resolver timeout" "Expected errors for timeout, got none"
    fi
    pass_test "Egg resolver timeout"
}

run_test test_egg_setup
run_test test_egg_string_inline
run_test test_egg_null_inline
run_test test_egg_object_inline
run_test test_egg_custom_resolver
run_test test_egg_resolver_timeout

# === FORMER PHASE 5 GROUP A: INDEX GENERATION ===

IB1=""
IB2=""

test_index_setup() {
    capture_cmd bees colonize-hive \
        --name "Index Hive" \
        --path "$REPO/tickets/index_hive"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Index setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    capture_cmd bees create-ticket --ticket-type bee --title "Index Bee A" \
        --hive index_hive --status worker
    IB1=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type bee --title "Index Bee B" \
        --hive index_hive --status pupa
    IB2=$(check_json "$CMD_OUT" "d['ticket_id']")
    pass_test "Index setup"
}

test_index_all_hives() {
    capture_cmd bees generate-index
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Generate index all hives" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Generate index all hives"
    # Check index.md was created in the index_hive directory
    if [ ! -f "$REPO/tickets/index_hive/index.md" ]; then
        fail_test "Generate index all hives" "index.md not found in index_hive directory"
    fi
    pass_test "Generate index all hives"
}

test_index_specific_hive() {
    capture_cmd bees generate-index --hive index_hive
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Generate index specific hive" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Generate index specific hive"
    # Verify index.md contains our ticket titles
    if ! grep -q "Index Bee A" "$REPO/tickets/index_hive/index.md"; then
        fail_test "Generate index specific hive" "index.md missing 'Index Bee A'"
    fi
    if ! grep -q "Index Bee B" "$REPO/tickets/index_hive/index.md"; then
        fail_test "Generate index specific hive" "index.md missing 'Index Bee B'"
    fi
    pass_test "Generate index specific hive"
}

run_test test_index_setup
run_test test_index_all_hives
run_test test_index_specific_hive

# === FORMER PHASE 5 GROUP A: UNDERTAKER ===

ARCH1=""
ARCH1_GUID=""

test_undertaker_setup() {
    capture_cmd bees colonize-hive \
        --name "Archive Hive" \
        --path "$REPO/tickets/archive_hive"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Undertaker setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    capture_cmd bees create-ticket --ticket-type bee --title "To Be Archived" \
        --hive archive_hive --status finished
    ARCH1=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees show-ticket --ids "$ARCH1"
    ARCH1_GUID=$(check_json "$CMD_OUT" "d['tickets'][0]['guid']")
    pass_test "Undertaker setup"
}

test_undertaker_yaml_query() {
    capture_cmd bees undertaker --hive archive_hive \
        --query-yaml "- [status=finished]"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Archive via YAML query" "exit $CMD_EXIT: $CMD_OUT"
    fi
    assert_no_traceback "$CMD_OUT" "Archive via YAML query"
    local archived_count
    archived_count=$(check_json "$CMD_OUT" "d.get('archived_count',0)")
    if [ "$archived_count" -lt 1 ]; then
        fail_test "Archive via YAML query" "Expected archived_count >= 1, got $archived_count"
    fi
    local has_guid
    has_guid=$(check_json "$CMD_OUT" "'$ARCH1_GUID' in d.get('archived_guids',[])")
    if [ "$has_guid" != "True" ]; then
        fail_test "Archive via YAML query" "ARCH1 GUID not in archived_guids"
    fi
    pass_test "Archive via YAML query"
}

test_undertaker_cemetery_guid_naming() {
    # Check that cemetery directory contains file named with the GUID
    local cemetery_dir="$REPO/tickets/archive_hive/cemetery"
    if [ ! -d "$cemetery_dir" ]; then
        fail_test "Cemetery GUID naming" "cemetery/ directory not found"
    fi
    # Find a file/dir matching the GUID — undertaker renames to prefix.guid, so search with wildcard
    local guid_file
    guid_file=$(find "$cemetery_dir" -name "*${ARCH1_GUID}*" -type f 2>/dev/null | head -1)
    if [ -z "$guid_file" ]; then
        # Also check for directory named by GUID
        guid_file=$(find "$cemetery_dir" -name "*${ARCH1_GUID}*" -type d 2>/dev/null | head -1)
    fi
    if [ -z "$guid_file" ]; then
        fail_test "Cemetery GUID naming" "No file/directory matching GUID '$ARCH1_GUID' in cemetery/"
    fi
    pass_test "Cemetery GUID naming"
}

test_undertaker_excluded_from_queries() {
    capture_cmd bees execute-freeform-query \
        --query-yaml "- [type=bee, hive=archive_hive]"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Archived excluded from queries" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_arch1
    has_arch1=$(check_json "$CMD_OUT" "'$ARCH1' in d.get('ticket_ids',[])")
    if [ "$has_arch1" != "False" ]; then
        fail_test "Archived excluded from queries" "Archived ticket $ARCH1 still appears in query results"
    fi
    pass_test "Archived excluded from queries"
}

test_undertaker_named_query() {
    # Register a named query for finished bees
    capture_cmd bees add-named-query --query-name "finished_bees" \
        --query-yaml "- [status=finished]" --scope global
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Archive via named query" "add-named-query failed: $CMD_OUT"
    fi
    # Create another finished bee
    capture_cmd bees create-ticket --ticket-type bee --title "Also Archived" \
        --hive archive_hive --status finished
    local arch2
    arch2=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees show-ticket --ids "$arch2"
    local arch2_guid
    arch2_guid=$(check_json "$CMD_OUT" "d['tickets'][0]['guid']")
    # Run undertaker with named query
    capture_cmd bees undertaker --hive archive_hive --query-name "finished_bees"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Archive via named query" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_guid
    has_guid=$(check_json "$CMD_OUT" "'$arch2_guid' in d.get('archived_guids',[])")
    if [ "$has_guid" != "True" ]; then
        fail_test "Archive via named query" "ARCH2 GUID not in archived_guids"
    fi
    # Clean up named query
    capture_cmd bees delete-named-query --query-name "finished_bees"
    pass_test "Archive via named query"
}

run_test test_undertaker_setup
run_test test_undertaker_yaml_query
run_test test_undertaker_cemetery_guid_naming
run_test test_undertaker_excluded_from_queries
run_test test_undertaker_named_query

# === FORMER PHASE 5 GROUP A: MOVE BEE ===

MOVEBEE=""
MOVETASK=""
MOVER=""

test_move_setup() {
    capture_cmd bees colonize-hive \
        --name "Move Source" \
        --path "$REPO/tickets/move_source" \
        --child-tiers '{"t1":["Task","Tasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Move setup" "Colonize source failed: $CMD_OUT"
    fi
    capture_cmd bees colonize-hive \
        --name "Move Dest" \
        --path "$REPO/tickets/move_dest"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Move setup" "Colonize dest failed: $CMD_OUT"
    fi
    capture_cmd bees create-ticket --ticket-type bee --title "Move Parent Bee" --hive move_source
    MOVEBEE=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t1 --title "Move Task" --hive move_source --parent "$MOVEBEE"
    MOVETASK=$(check_json "$CMD_OUT" "d['ticket_id']")
    pass_test "Move setup"
}

test_move_bee_between_hives() {
    capture_cmd bees create-ticket --ticket-type bee --title "Mover Bee" --hive move_source
    MOVER=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees move-bee --ids "$MOVER" --hive move_dest
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Move bee between hives" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_moved
    has_moved=$(check_json "$CMD_OUT" "'$MOVER' in d.get('moved',[])")
    if [ "$has_moved" != "True" ]; then
        fail_test "Move bee between hives" "MOVER not in moved list"
    fi
    pass_test "Move bee between hives"
}

test_move_bee_id_preserved() {
    capture_cmd bees show-ticket --ids "$MOVER"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Bee ID preserved after move" "Show failed: $CMD_OUT"
    fi
    local shown_id
    shown_id=$(check_json "$CMD_OUT" "d['tickets'][0]['ticket_id']")
    if [ "$shown_id" != "$MOVER" ]; then
        fail_test "Bee ID preserved after move" "Expected $MOVER, got $shown_id"
    fi
    pass_test "Bee ID preserved after move"
}

test_move_reject_non_bee() {
    capture_cmd bees move-bee --ids "$MOVETASK" --hive move_dest
    if [ "$CMD_EXIT" -eq 0 ]; then
        # Check if it's in the failed list
        local in_failed
        in_failed=$(check_json "$CMD_OUT" "len(d.get('failed',[])) > 0")
        if [ "$in_failed" != "True" ]; then
            fail_test "Reject non-bee on move" "Expected failure for non-bee ticket"
        fi
    fi
    assert_no_traceback "$CMD_OUT" "Reject non-bee on move"
    pass_test "Reject non-bee on move"
}

test_move_already_in_dest() {
    capture_cmd bees move-bee --ids "$MOVER" --hive move_dest
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Skip already-in-dest" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local in_skipped
    in_skipped=$(check_json "$CMD_OUT" "'$MOVER' in d.get('skipped',[])")
    if [ "$in_skipped" != "True" ]; then
        fail_test "Skip already-in-dest" "MOVER not in skipped list"
    fi
    pass_test "Skip already-in-dest"
}

test_move_friendly_name_dest() {
    # Create a fresh bee to move using the display name "Move Source"
    capture_cmd bees create-ticket --ticket-type bee --title "Friendly Move Bee" --hive move_dest
    local friendly_bee
    friendly_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    # Move using display name (not normalized)
    capture_cmd bees move-bee --ids "$friendly_bee" --hive "Move Source"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Friendly name dest" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_moved
    has_moved=$(check_json "$CMD_OUT" "'$friendly_bee' in d.get('moved',[])")
    if [ "$has_moved" != "True" ]; then
        fail_test "Friendly name dest" "Bee not in moved list"
    fi
    pass_test "Friendly name dest"
}

test_move_blocked_by_status_values() {
    # Create source and dest hives for compatibility tests
    capture_cmd bees colonize-hive \
        --name "Compat Source" \
        --path "$REPO/tickets/compat_source"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Move blocked by status_values" "Colonize source failed: $CMD_OUT"
    fi
    capture_cmd bees colonize-hive \
        --name "Compat Dest" \
        --path "$REPO/tickets/compat_dest"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Move blocked by status_values" "Colonize dest failed: $CMD_OUT"
    fi
    # Set restricted status_values on dest
    capture_cmd bees set-status-values --scope hive --hive "Compat Dest" \
        --status-values '["open","done"]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Move blocked by status_values" "set-status-values failed: $CMD_OUT"
    fi
    # Create bee in source with status not in dest's allowed values
    capture_cmd bees create-ticket --ticket-type bee --title "Compat Bee" \
        --hive compat_source --status worker
    local compat_bee
    compat_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    # Try to move without --force
    capture_cmd bees move-bee --ids "$compat_bee" --hive compat_dest
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Move blocked by status_values" "Expected failure but got success"
    fi
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    if [ "$error_type" != "compatibility_error" ]; then
        fail_test "Move blocked by status_values" "Expected compatibility_error, got $error_type"
    fi
    pass_test "Move blocked by status_values"
}

test_move_blocked_by_tiers() {
    # Source hive with t1+t2 tiers
    capture_cmd bees colonize-hive \
        --name "Tier Source" \
        --path "$REPO/tickets/tier_source" \
        --child-tiers '{"t1":["Task","Tasks"],"t2":["Subtask","Subtasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Move blocked by tiers" "Colonize source failed: $CMD_OUT"
    fi
    # Dest hive with t1-only tiers
    capture_cmd bees colonize-hive \
        --name "Tier Dest" \
        --path "$REPO/tickets/tier_dest" \
        --child-tiers '{"t1":["Task","Tasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Move blocked by tiers" "Colonize dest failed: $CMD_OUT"
    fi
    # Create bee with t1 child and t2 grandchild
    capture_cmd bees create-ticket --ticket-type bee --title "Tier Bee" --hive tier_source
    local tier_bee
    tier_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t1 --title "Tier Task" --hive tier_source --parent "$tier_bee"
    local tier_task
    tier_task=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t2 --title "Tier Subtask" --hive tier_source --parent "$tier_task"
    # Move without --force should fail due to t2 incompatibility
    capture_cmd bees move-bee --ids "$tier_bee" --hive tier_dest
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Move blocked by tiers" "Expected failure but got success"
    fi
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    if [ "$error_type" != "compatibility_error" ]; then
        fail_test "Move blocked by tiers" "Expected compatibility_error, got $error_type"
    fi
    pass_test "Move blocked by tiers"
}

test_move_force_bypass() {
    # Use the compat_bee from the status_values test (still in compat_source)
    capture_cmd bees execute-freeform-query \
        --query-yaml "- [type=bee, hive=compat_source, title~Compat Bee]"
    local force_bee
    force_bee=$(check_json "$CMD_OUT" "d['ticket_ids'][0]")
    capture_cmd bees move-bee --ids "$force_bee" --hive compat_dest --force
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Force bypass move" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_moved
    has_moved=$(check_json "$CMD_OUT" "'$force_bee' in d.get('moved',[])")
    if [ "$has_moved" != "True" ]; then
        fail_test "Force bypass move" "Bee not in moved list"
    fi
    pass_test "Force bypass move"
}

run_test test_move_setup
run_test test_move_bee_between_hives
run_test test_move_bee_id_preserved
run_test test_move_reject_non_bee
run_test test_move_already_in_dest
run_test test_move_friendly_name_dest
run_test test_move_blocked_by_status_values
run_test test_move_blocked_by_tiers
run_test test_move_force_bypass

# === FORMER PHASE 5 GROUP A: SANITIZER ===

SAN_BEE=""
SAN_TASK=""

test_sanitizer_setup() {
    capture_cmd bees colonize-hive \
        --name "Sanitizer Hive" \
        --path "$REPO/tickets/sanitizer_hive" \
        --child-tiers '{"t1":["Task","Tasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Sanitizer setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    capture_cmd bees create-ticket --ticket-type bee --title "Sanitizer Bee" --hive sanitizer_hive
    SAN_BEE=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t1 --title "Sanitizer Task" \
        --hive sanitizer_hive --parent "$SAN_BEE"
    SAN_TASK=$(check_json "$CMD_OUT" "d['ticket_id']")
    pass_test "Sanitizer setup"
}

test_sanitizer_clean_hive() {
    capture_cmd bees sanitize-hive --hive "Sanitizer Hive"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Clean hive is_corrupt false" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local is_corrupt
    is_corrupt=$(check_json "$CMD_OUT" "d.get('is_corrupt', True)")
    if [ "$is_corrupt" != "False" ]; then
        fail_test "Clean hive is_corrupt false" "Expected is_corrupt=False, got $is_corrupt"
    fi
    local fix_count
    fix_count=$(check_json "$CMD_OUT" "len(d.get('fixes_applied',[]))")
    if [ "$fix_count" != "0" ]; then
        fail_test "Clean hive is_corrupt false" "Expected 0 fixes, got $fix_count"
    fi
    pass_test "Clean hive is_corrupt false"
}

test_sanitizer_broken_bidir_ref() {
    # Remove SAN_TASK from SAN_BEE's children list (break bidirectional ref)
    local bee_file
    bee_file=$(find "$REPO/tickets/sanitizer_hive" -name "${SAN_BEE}*" -type f 2>/dev/null | head -1)
    if [ -z "$bee_file" ]; then
        # Try broader search
        bee_file=$(find "$REPO/tickets/sanitizer_hive" -name "*.md" ! -path '*/cemetery/*' ! -path '*/.hive/*' | xargs grep -l "^id: $SAN_BEE$" 2>/dev/null | head -1)
    fi
    if [ -z "$bee_file" ]; then
        fail_test "Broken bidir ref fix" "Could not find SAN_BEE file"
    fi
    python3 -c "
import pathlib, re
f = pathlib.Path('$bee_file')
t = f.read_text()
# Remove children block entirely (header + all block-style list items)
t = re.sub(r'children:.*\n(?:- [^\n]*\n)*', '', t)
f.write_text(t)
"
    # Run sanitizer — should detect and fix
    capture_cmd bees sanitize-hive --hive "Sanitizer Hive"
    assert_no_traceback "$CMD_OUT" "Broken bidir ref fix"
    local fix_count
    fix_count=$(check_json "$CMD_OUT" "len(d.get('fixes_applied',[]))")
    if [ "$fix_count" -lt 1 ]; then
        fail_test "Broken bidir ref fix" "Expected at least 1 fix, got $fix_count"
    fi
    # Run again — should now be clean
    capture_cmd bees sanitize-hive --hive "Sanitizer Hive"
    local is_corrupt
    is_corrupt=$(check_json "$CMD_OUT" "d.get('is_corrupt', True)")
    if [ "$is_corrupt" != "False" ]; then
        fail_test "Broken bidir ref fix" "Expected is_corrupt=False after fix"
    fi
    pass_test "Broken bidir ref fix"
}

test_sanitizer_disallowed_fields() {
    # Add a disallowed field "owner" to SAN_BEE's frontmatter
    local bee_file
    bee_file=$(find "$REPO/tickets/sanitizer_hive" -name "*.md" ! -path '*/cemetery/*' ! -path '*/.hive/*' | xargs grep -l "^id: $SAN_BEE$" 2>/dev/null | head -1)
    if [ -z "$bee_file" ]; then
        fail_test "Disallowed fields" "Could not find SAN_BEE file"
    fi
    python3 -c "
import pathlib
f = pathlib.Path('$bee_file')
t = f.read_text()
# Add 'owner' field after 'id' line
t = t.replace('id: $SAN_BEE', 'id: $SAN_BEE\nowner: someone', 1)
f.write_text(t)
"
    capture_cmd bees sanitize-hive --hive "Sanitizer Hive"
    assert_no_traceback "$CMD_OUT" "Disallowed fields"
    local has_disallowed
    has_disallowed=$(check_json "$CMD_OUT" "any(e.get('error_type')=='disallowed_field' for e in d.get('errors_remaining',[]))")
    if [ "$has_disallowed" != "True" ]; then
        fail_test "Disallowed fields" "Expected disallowed_field error in errors_remaining"
    fi
    # Clean up: remove the owner field
    python3 -c "
import pathlib
f = pathlib.Path('$bee_file')
t = f.read_text()
t = t.replace('owner: someone\n', '')
f.write_text(t)
"
    pass_test "Disallowed fields"
}

test_sanitizer_dangling_dep() {
    # Create a bee with a dangling dependency injected via frontmatter
    capture_cmd bees create-ticket --ticket-type bee --title "Dang Dep Bee" --hive sanitizer_hive
    local dang_bee
    dang_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    local dang_file
    dang_file=$(find "$REPO/tickets/sanitizer_hive" -name "*.md" ! -path '*/cemetery/*' ! -path '*/.hive/*' | xargs grep -l "^id: $dang_bee$" 2>/dev/null | head -1)
    python3 -c "
import pathlib, re
f = pathlib.Path('$dang_file')
t = f.read_text()
# Inject a dangling dependency before the closing --- (field may not exist if empty)
if re.search(r'^up_dependencies:', t, re.MULTILINE):
    t = re.sub(r'up_dependencies:.*\n(?:- [^\n]*\n)*', 'up_dependencies:\n- b.zzz\n', t)
else:
    t = re.sub(r'\n---\n', '\nup_dependencies:\n- b.zzz\n---\n', t, count=1)
f.write_text(t)
"
    capture_cmd bees sanitize-hive --hive "Sanitizer Hive"
    assert_no_traceback "$CMD_OUT" "Dangling dependency"
    local has_dangling
    has_dangling=$(check_json "$CMD_OUT" "any(e.get('error_type')=='dangling_dependency' for e in d.get('errors_remaining',[]))")
    if [ "$has_dangling" != "True" ]; then
        fail_test "Dangling dependency" "Expected dangling_dependency error"
    fi
    pass_test "Dangling dependency"
}

test_sanitizer_dangling_parent() {
    # Edit SAN_TASK's parent to a non-existent ID
    local task_file
    task_file=$(find "$REPO/tickets/sanitizer_hive" -name "*.md" ! -path '*/cemetery/*' ! -path '*/.hive/*' | xargs grep -l "^id: $SAN_TASK$" 2>/dev/null | head -1)
    if [ -z "$task_file" ]; then
        fail_test "Dangling parent" "Could not find SAN_TASK file"
    fi
    # Save original parent for restore
    local original_parent="$SAN_BEE"
    python3 -c "
import pathlib, re
f = pathlib.Path('$task_file')
t = f.read_text()
t = re.sub(r'parent: .*', 'parent: b.zzz', t)
f.write_text(t)
"
    capture_cmd bees sanitize-hive --hive "Sanitizer Hive"
    assert_no_traceback "$CMD_OUT" "Dangling parent"
    local has_dangling
    has_dangling=$(check_json "$CMD_OUT" "any(e.get('error_type')=='dangling_parent' for e in d.get('errors_remaining',[]))")
    if [ "$has_dangling" != "True" ]; then
        fail_test "Dangling parent" "Expected dangling_parent error"
    fi
    # Restore parent
    python3 -c "
import pathlib, re
f = pathlib.Path('$task_file')
t = f.read_text()
t = re.sub(r'parent: .*', 'parent: $original_parent', t)
f.write_text(t)
"
    pass_test "Dangling parent"
}

test_sanitizer_auto_fix_dangling_dep() {
    # Enable auto_fix_dangling_refs
    python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.bees' / 'config.json'
d = json.loads(p.read_text())
d['auto_fix_dangling_refs'] = True
p.write_text(json.dumps(d))
"
    # Create a bee with dangling dep
    capture_cmd bees create-ticket --ticket-type bee --title "Auto Fix Dep Bee" --hive sanitizer_hive
    local af_bee
    af_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    local af_file
    af_file=$(find "$REPO/tickets/sanitizer_hive" -name "*.md" ! -path '*/cemetery/*' ! -path '*/.hive/*' | xargs grep -l "^id: $af_bee$" 2>/dev/null | head -1)
    python3 -c "
import pathlib, re
f = pathlib.Path('$af_file')
t = f.read_text()
# Inject a dangling dependency before the closing --- (field may not exist if empty)
if re.search(r'^up_dependencies:', t, re.MULTILINE):
    t = re.sub(r'up_dependencies:.*\n(?:- [^\n]*\n)*', 'up_dependencies:\n- b.yyy\n', t)
else:
    t = re.sub(r'\n---\n', '\nup_dependencies:\n- b.yyy\n---\n', t, count=1)
f.write_text(t)
"
    capture_cmd bees sanitize-hive --hive "Sanitizer Hive"
    assert_no_traceback "$CMD_OUT" "Auto-fix dangling dep"
    local has_fix
    has_fix=$(check_json "$CMD_OUT" "any(f.get('fix_type')=='remove_dangling_dependency' for f in d.get('fixes_applied',[]))")
    if [ "$has_fix" != "True" ]; then
        fail_test "Auto-fix dangling dep" "Expected remove_dangling_dependency fix"
    fi
    # Verify the dep was actually removed
    capture_cmd bees show-ticket --ids "$af_bee"
    local has_dep
    has_dep=$(check_json "$CMD_OUT" "'b.yyy' in (d['tickets'][0].get('up_dependencies') or [])")
    if [ "$has_dep" != "False" ]; then
        fail_test "Auto-fix dangling dep" "b.yyy still in up_dependencies after auto-fix"
    fi
    # Remove auto_fix_dangling_refs
    python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.bees' / 'config.json'
d = json.loads(p.read_text())
d.pop('auto_fix_dangling_refs', None)
p.write_text(json.dumps(d))
"
    pass_test "Auto-fix dangling dep"
}

test_sanitizer_auto_fix_dangling_parent() {
    # Enable auto_fix_dangling_refs
    python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.bees' / 'config.json'
d = json.loads(p.read_text())
d['auto_fix_dangling_refs'] = True
p.write_text(json.dumps(d))
"
    # Create a task under SAN_BEE, then break its parent
    capture_cmd bees create-ticket --ticket-type t1 --title "Auto Fix Task" \
        --hive sanitizer_hive --parent "$SAN_BEE"
    local af_task
    af_task=$(check_json "$CMD_OUT" "d['ticket_id']")
    local af_file
    af_file=$(find "$REPO/tickets/sanitizer_hive" -name "*.md" ! -path '*/cemetery/*' ! -path '*/.hive/*' | xargs grep -l "^id: $af_task$" 2>/dev/null | head -1)
    python3 -c "
import pathlib, re
f = pathlib.Path('$af_file')
t = f.read_text()
t = re.sub(r'parent: .*', 'parent: b.zzz', t)
f.write_text(t)
"
    capture_cmd bees sanitize-hive --hive "Sanitizer Hive"
    assert_no_traceback "$CMD_OUT" "Auto-fix dangling parent"
    local has_fix
    has_fix=$(check_json "$CMD_OUT" "any(f.get('fix_type')=='clear_dangling_parent' for f in d.get('fixes_applied',[]))")
    if [ "$has_fix" != "True" ]; then
        fail_test "Auto-fix dangling parent" "Expected clear_dangling_parent fix"
    fi
    # Verify parent was cleared by checking the ticket file directly
    # (show-ticket uses compute_ticket_path which can't find the moved ticket)
    local af_task_file
    af_task_file=$(find "$REPO/tickets/sanitizer_hive" -name "${af_task}.md" -type f 2>/dev/null | head -1)
    if [ -z "$af_task_file" ]; then
        fail_test "Auto-fix dangling parent" "Could not find af_task file after sanitizer"
    fi
    local parent_val
    parent_val=$(python3 -c "
import pathlib, re
t = pathlib.Path('$af_task_file').read_text()
m = re.search(r'^parent: (.*)$', t, re.MULTILINE)
print(m.group(1).strip() if m else 'None')
")
    if [ "$parent_val" != "None" ] && [ "$parent_val" != "null" ] && [ -n "$parent_val" ]; then
        fail_test "Auto-fix dangling parent" "Parent not cleared, got '$parent_val'"
    fi
    # Remove auto_fix_dangling_refs
    python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.bees' / 'config.json'
d = json.loads(p.read_text())
d.pop('auto_fix_dangling_refs', None)
p.write_text(json.dumps(d))
"
    pass_test "Auto-fix dangling parent"
}

run_test test_sanitizer_setup
run_test test_sanitizer_clean_hive
run_test test_sanitizer_broken_bidir_ref
run_test test_sanitizer_disallowed_fields
run_test test_sanitizer_dangling_dep
run_test test_sanitizer_dangling_parent
run_test test_sanitizer_auto_fix_dangling_dep
run_test test_sanitizer_auto_fix_dangling_parent

# === FORMER PHASE 5 GROUP A: ERROR HANDLING ===

ERR_BEE=""
ERR_TASK=""

test_error_setup() {
    capture_cmd bees colonize-hive \
        --name "Error Hive" \
        --path "$REPO/tickets/error_hive" \
        --child-tiers '{"t1":["Task","Tasks"],"t2":["Subtask","Subtasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Error setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    capture_cmd bees create-ticket --ticket-type bee --title "Error Bee" --hive error_hive
    ERR_BEE=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t1 --title "Error Task" \
        --hive error_hive --parent "$ERR_BEE"
    ERR_TASK=$(check_json "$CMD_OUT" "d['ticket_id']")
    pass_test "Error setup"
}

test_error_invalid_id() {
    capture_cmd bees show-ticket --ids "invalid!!!"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Invalid ID format" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "Invalid ID format"
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    if [ "$error_type" != "invalid_ticket_id" ]; then
        fail_test "Invalid ID format" "Expected error_type=invalid_ticket_id, got $error_type"
    fi
    pass_test "Invalid ID format"
}

test_error_missing_on_show() {
    capture_cmd bees show-ticket --ids "b.zzz"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Missing ticket on show" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local nf_count
    nf_count=$(check_json "$CMD_OUT" "len(d.get('not_found',[]))")
    if [ "$nf_count" -lt 1 ]; then
        fail_test "Missing ticket on show" "Expected not_found to contain b.zzz"
    fi
    pass_test "Missing ticket on show"
}

test_error_missing_on_update() {
    capture_cmd bees update-ticket --ticket-id "b.zzz" --title "Ghost"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Missing ticket on update" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "Missing ticket on update"
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    if [ "$error_type" != "ticket_not_found" ]; then
        fail_test "Missing ticket on update" "Expected error_type=ticket_not_found, got $error_type"
    fi
    pass_test "Missing ticket on update"
}

test_error_missing_on_delete() {
    capture_cmd bees delete-ticket --ids "b.zzz"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Missing ticket on delete" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "Missing ticket on delete"
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    if [ "$error_type" != "ticket_not_found" ]; then
        fail_test "Missing ticket on delete" "Expected error_type=ticket_not_found, got $error_type"
    fi
    pass_test "Missing ticket on delete"
}

test_error_duplicate_hive() {
    capture_cmd bees colonize-hive \
        --name "Error Hive" \
        --path "$REPO/tickets/error_hive_dupe"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Duplicate hive name" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "Duplicate hive name"
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    if [ "$error_type" != "duplicate_hive_name" ]; then
        fail_test "Duplicate hive name" "Expected error_type=duplicate_hive_name, got $error_type"
    fi
    pass_test "Duplicate hive name"
}

test_error_invalid_yaml_query() {
    capture_cmd bees execute-freeform-query --query-yaml "not valid yaml ["
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Invalid YAML query" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "Invalid YAML query"
    local status
    status=$(check_json "$CMD_OUT" "d.get('status','')")
    if [ "$status" != "error" ]; then
        fail_test "Invalid YAML query" "Expected status=error, got $status"
    fi
    pass_test "Invalid YAML query"
}

test_error_wrong_tier_parent() {
    # Try to create t2 directly under a bee (skipping t1)
    capture_cmd bees create-ticket --ticket-type t2 --title "Bad Subtask" \
        --hive error_hive --parent "$ERR_BEE"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Wrong tier parent" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "Wrong tier parent"
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    if [ "$error_type" != "invalid_parent" ]; then
        fail_test "Wrong tier parent" "Expected error_type=invalid_parent, got $error_type"
    fi
    pass_test "Wrong tier parent"
}

test_error_missing_required_flags() {
    # Create a ticket without --title (required flag)
    capture_cmd bees create-ticket --ticket-type bee --hive error_hive
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Missing required flags" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "Missing required flags"
    pass_test "Missing required flags"
}

run_test test_error_setup
run_test test_error_invalid_id
run_test test_error_missing_on_show
run_test test_error_missing_on_update
run_test test_error_missing_on_delete
run_test test_error_duplicate_hive
run_test test_error_invalid_yaml_query
run_test test_error_wrong_tier_parent
run_test test_error_missing_required_flags

# === FORMER PHASE 5 GROUP B: TEST CONFIG MODE ===

test_testconfig_bare() {
    capture_cmd bees list-hives --test-config
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Bare --test-config" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local hive_count
    hive_count=$(check_json "$CMD_OUT" "len(d.get('hives',[]))")
    if [ "$hive_count" != "0" ]; then
        fail_test "Bare --test-config" "Expected 0 hives, got $hive_count"
    fi
    pass_test "Bare --test-config"
}

test_testconfig_inline_json() {
    local tc_json='{"schema_version":"0.1","scopes":{"/test-repo/**":{"hives":{"phantom_hive":{"path":"/tmp/phantom","display_name":"Phantom Hive"}}}}}'
    capture_cmd bees list-hives --test-config "$tc_json"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Inline JSON test-config" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_phantom
    has_phantom=$(check_json "$CMD_OUT" "any(h.get('normalized_name')=='phantom_hive' for h in d.get('hives',[]))")
    if [ "$has_phantom" != "True" ]; then
        fail_test "Inline JSON test-config" "Phantom hive not found in list"
    fi
    pass_test "Inline JSON test-config"
}

test_testconfig_file() {
    local tc_file="$REPO/test_config.json"
    cat > "$tc_file" << 'TCEOF'
{"schema_version":"0.1","scopes":{"/test-repo/**":{"hives":{"file_hive":{"path":"/tmp/filehive","display_name":"File Hive"}}}}}
TCEOF
    capture_cmd bees list-hives --test-config "$tc_file"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "File-based test-config" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local has_file_hive
    has_file_hive=$(check_json "$CMD_OUT" "any(h.get('normalized_name')=='file_hive' for h in d.get('hives',[]))")
    if [ "$has_file_hive" != "True" ]; then
        fail_test "File-based test-config" "File hive not found in list"
    fi
    rm -f "$tc_file"
    pass_test "File-based test-config"
}

test_testconfig_no_disk_write() {
    local config_file="$HOME/.bees/config.json"
    local mtime_before
    mtime_before=$(stat -c %Y "$config_file" 2>/dev/null || stat -f %m "$config_file")
    # Run mutating commands with --test-config
    capture_cmd bees colonize-hive --name "Ghost Hive" --path /tmp/ghost --test-config
    capture_cmd bees list-hives --test-config
    local mtime_after
    mtime_after=$(stat -c %Y "$config_file" 2>/dev/null || stat -f %m "$config_file")
    if [ "$mtime_before" != "$mtime_after" ]; then
        fail_test "test-config no disk write" "config.json mtime changed: $mtime_before -> $mtime_after"
    fi
    pass_test "test-config no disk write"
}

run_test test_testconfig_bare
run_test test_testconfig_inline_json
run_test test_testconfig_file
run_test test_testconfig_no_disk_write

# === FORMER PHASE 5 GROUP B: SETUP COMMAND ===

test_setup_install_global() {
    capture_cmd bees setup claude cli
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Setup install global" "exit $CMD_EXIT: $CMD_OUT"
    fi
    # Check output message
    if ! echo "$CMD_OUT" | grep -q "Installed bees sting hooks in\|already present"; then
        fail_test "Setup install global" "Expected install/already-present message"
    fi
    # Check settings.json contains hooks
    local settings_file="$HOME/.claude/settings.json"
    if [ -f "$settings_file" ]; then
        local has_hooks
        has_hooks=$(python3 -c "
import json
d = json.load(open('$settings_file'))
hooks = d.get('hooks', {})
def has_sting(event):
    for group in hooks.get(event, []):
        if isinstance(group, dict):
            for h in group.get('hooks', []):
                if 'bees sting' in h.get('command', ''):
                    return True
    return False
print(has_sting('SessionStart') and has_sting('PreCompact'))
")
        if [ "$has_hooks" != "True" ]; then
            fail_test "Setup install global" "hooks not found in settings.json"
        fi
    fi
    pass_test "Setup install global"
}

test_setup_install_idempotent() {
    capture_cmd bees setup claude cli
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Setup idempotent" "exit $CMD_EXIT: $CMD_OUT"
    fi
    if ! echo "$CMD_OUT" | grep -q "already present"; then
        fail_test "Setup idempotent" "Expected 'already present' message"
    fi
    pass_test "Setup idempotent"
}

test_setup_install_project() {
    capture_cmd bees setup claude cli --project
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Setup with --project" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local local_settings="$REPO/.claude/settings.local.json"
    if [ -f "$local_settings" ]; then
        local has_hooks
        has_hooks=$(python3 -c "
import json
d = json.load(open('$local_settings'))
hooks = d.get('hooks', {})
def has_sting(event):
    for group in hooks.get(event, []):
        if isinstance(group, dict):
            for h in group.get('hooks', []):
                if 'bees sting' in h.get('command', ''):
                    return True
    return False
print(has_sting('SessionStart'))
")
        if [ "$has_hooks" != "True" ]; then
            fail_test "Setup with --project" "hooks not found in settings.local.json"
        fi
    fi
    pass_test "Setup with --project"
}

test_setup_remove() {
    capture_cmd bees setup claude cli --remove
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Setup --remove" "exit $CMD_EXIT: $CMD_OUT"
    fi
    if ! echo "$CMD_OUT" | grep -q "Removed bees sting hooks from"; then
        fail_test "Setup --remove" "Expected 'Removed' message"
    fi
    pass_test "Setup --remove"
}

test_setup_remove_idempotent() {
    capture_cmd bees setup claude cli --remove
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Setup --remove idempotent" "exit $CMD_EXIT: $CMD_OUT"
    fi
    if ! echo "$CMD_OUT" | grep -q "No bees sting hooks found in"; then
        fail_test "Setup --remove idempotent" "Expected 'No bees sting hooks found' message"
    fi
    pass_test "Setup --remove idempotent"
}

run_test test_setup_install_global
run_test test_setup_install_idempotent
run_test test_setup_install_project
run_test test_setup_remove
run_test test_setup_remove_idempotent

# === FORMER PHASE 5 GROUP B: STING COMMAND ===

test_sting_setup() {
    capture_cmd bees colonize-hive \
        --name "Sting Hive" \
        --path "$REPO/tickets/sting_hive"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Sting setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    pass_test "Sting setup"
}

test_sting_in_scope() {
    capture_cmd bees sting
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Sting in scope" "exit $CMD_EXIT: $CMD_OUT"
    fi
    # Output may be empty (MCP-mode) or contain CLI reference — both valid
    assert_no_traceback "$CMD_OUT" "Sting in scope"
    pass_test "Sting in scope"
}

test_sting_outside_scope() {
    capture_cmd bees sting --test-config
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Sting outside scope" "exit $CMD_EXIT: $CMD_OUT"
    fi
    pass_test "Sting outside scope"
}

run_test test_sting_setup
run_test test_sting_in_scope
run_test test_sting_outside_scope

# === FORMER PHASE 5 GROUP B: STATUS VALUES ===

test_sv_setup() {
    capture_cmd bees colonize-hive \
        --name "SV Hive" \
        --path "$REPO/tickets/sv_hive"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "SV setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    # Ensure no global status_values
    capture_cmd bees set-status-values --scope global --unset
    pass_test "SV setup"
}

test_sv_set_global() {
    capture_cmd bees set-status-values --scope global \
        --status-values '["pupa","worker","finished"]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Set status_values global" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local scope
    scope=$(check_json "$CMD_OUT" "d.get('scope','')")
    assert_eq "$scope" "global" "Set status_values global"
}

test_sv_set_repo_scope() {
    capture_cmd bees set-status-values --scope repo_scope \
        --status-values '["pupa","worker"]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Set status_values repo_scope" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local scope
    scope=$(check_json "$CMD_OUT" "d.get('scope','')")
    assert_eq "$scope" "repo_scope" "Set status_values repo_scope"
}

test_sv_set_hive() {
    capture_cmd bees set-status-values --scope hive --hive "SV Hive" \
        --status-values '["pupa","worker","finished"]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Set status_values hive" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local scope hive_name
    scope=$(check_json "$CMD_OUT" "d.get('scope','')")
    hive_name=$(check_json "$CMD_OUT" "d.get('hive_name','')")
    if [ "$scope" != "hive" ] || [ "$hive_name" != "sv_hive" ]; then
        fail_test "Set status_values hive" "Expected scope=hive, hive_name=sv_hive"
    fi
    pass_test "Set status_values hive"
}

test_sv_unset_global() {
    capture_cmd bees set-status-values --scope global --unset
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Unset status_values global" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local scope
    scope=$(check_json "$CMD_OUT" "d.get('scope','')")
    assert_eq "$scope" "global" "Unset status_values global"
}

test_sv_error_missing_values() {
    capture_cmd bees set-status-values --scope global
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Error missing_status_values" "Expected failure but got success"
    fi
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    assert_eq "$error_type" "missing_status_values" "Error missing_status_values"
}

test_sv_error_missing_hive_name() {
    capture_cmd bees set-status-values --scope hive --status-values '["x"]'
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Error missing_hive_name" "Expected failure but got success"
    fi
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    assert_eq "$error_type" "missing_hive_name" "Error missing_hive_name"
}

test_sv_get_mixed() {
    capture_cmd bees get-status-values
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Get status_values mixed" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local global_val scope_val hive_val
    global_val=$(check_json "$CMD_OUT" "d.get('global')")
    scope_val=$(check_json "$CMD_OUT" "d.get('scope')")
    hive_val=$(check_json "$CMD_OUT" "d.get('hives',{}).get('sv_hive')")
    # Global was unset in test_sv_unset_global
    if [ "$global_val" != "None" ]; then
        fail_test "Get status_values mixed" "Expected global=None, got $global_val"
    fi
    # Repo scope was set to [pupa,worker]
    if [ "$scope_val" = "None" ]; then
        fail_test "Get status_values mixed" "Expected scope to be set"
    fi
    pass_test "Get status_values mixed"
}

test_sv_create_required_but_missing() {
    # sv_hive has status_values configured, so status is required
    capture_cmd bees create-ticket --ticket-type bee --title "SV Required Test" --hive sv_hive
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Create without required status" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "Create without required status"
    pass_test "Create without required status"
}

test_sv_create_no_config_no_status() {
    # Unset hive status_values so no validation
    capture_cmd bees set-status-values --scope hive --hive "SV Hive" --unset
    capture_cmd bees create-ticket --ticket-type bee --title "SV No Config Test" --hive sv_hive
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Create no config no status" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local sv_bee
    sv_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees show-ticket --ids "$sv_bee"
    local status_val
    status_val=$(check_json "$CMD_OUT" "d['tickets'][0].get('ticket_status')")
    if [ "$status_val" != "None" ]; then
        fail_test "Create no config no status" "Expected null status, got $status_val"
    fi
    pass_test "Create no config no status"
}

test_sv_create_invalid_status() {
    # Re-configure hive status_values
    capture_cmd bees set-status-values --scope hive --hive "SV Hive" \
        --status-values '["pupa","worker","finished"]'
    capture_cmd bees create-ticket --ticket-type bee --title "SV Invalid Status Test" \
        --hive sv_hive --status bogus
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Create with invalid status" "Expected failure but got success"
    fi
    assert_no_traceback "$CMD_OUT" "Create with invalid status"
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    if [ "$error_type" != "invalid_status" ]; then
        fail_test "Create with invalid status" "Expected error_type=invalid_status, got $error_type"
    fi
    # Teardown: unset at all scopes
    capture_cmd bees set-status-values --scope global --unset
    capture_cmd bees set-status-values --scope repo_scope --unset
    pass_test "Create with invalid status"
}

run_test test_sv_setup
run_test test_sv_set_global
run_test test_sv_set_repo_scope
run_test test_sv_set_hive
run_test test_sv_unset_global
run_test test_sv_error_missing_values
run_test test_sv_error_missing_hive_name
run_test test_sv_get_mixed
run_test test_sv_create_required_but_missing
run_test test_sv_create_no_config_no_status
run_test test_sv_create_invalid_status

# === FORMER PHASE 5 GROUP B: UNINSTALL SEQUENCE ===

test_uninstall_remove_hooks() {
    # Ensure hooks are installed first
    capture_cmd bees setup claude cli
    capture_cmd bees setup claude cli --remove
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Uninstall remove hooks" "exit $CMD_EXIT: $CMD_OUT"
    fi
    if ! echo "$CMD_OUT" | grep -q "Removed bees sting hooks from"; then
        fail_test "Uninstall remove hooks" "Expected 'Removed' message"
    fi
    pass_test "Uninstall remove hooks"
}

test_uninstall_pipx_cycle() {
    # Install via pipx using the version already installed
    local bees_version
    bees_version=$(bees --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "")
    if [ -z "$bees_version" ]; then
        # Skip if version can't be determined
        pass_test "Uninstall pipx cycle (skipped: version unknown)"
        return
    fi
    capture_cmd pipx install "bees-md[serve]==$bees_version" \
        --pip-args="--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/" 2>&1
    # pipx install may fail if already installed system-wide — that's okay
    if [ -f "$HOME/.local/bin/bees" ]; then
        capture_cmd pipx uninstall bees-md
        if [ "$CMD_EXIT" -ne 0 ]; then
            fail_test "Uninstall pipx cycle" "pipx uninstall failed: $CMD_OUT"
        fi
        if [ -f "$HOME/.local/bin/bees" ]; then
            fail_test "Uninstall pipx cycle" "~/.local/bin/bees still exists after uninstall"
        fi
    fi
    pass_test "Uninstall pipx cycle"
}

run_test test_uninstall_remove_hooks
run_test test_uninstall_pipx_cycle

# === FORMER PHASE 5 GROUP B: CLONE BEE ===

CLONE_BEE=""
CLONE_TASK1=""
CLONE_TASK2=""

test_clone_setup() {
    capture_cmd bees colonize-hive \
        --name "Clone Hive" \
        --path "$REPO/tickets/clone_hive" \
        --child-tiers '{"t1":["Task","Tasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Clone setup" "exit $CMD_EXIT: $CMD_OUT"
    fi
    capture_cmd bees create-ticket --ticket-type bee --title "Clone Source Bee" \
        --hive clone_hive --status pupa --tags '["cloneable"]' --egg '"clone_egg"'
    CLONE_BEE=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t1 --title "Clone Task 1" \
        --hive clone_hive --parent "$CLONE_BEE"
    CLONE_TASK1=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t1 --title "Clone Task 2" \
        --hive clone_hive --parent "$CLONE_BEE"
    CLONE_TASK2=$(check_json "$CMD_OUT" "d['ticket_id']")
    pass_test "Clone setup"
}

test_clone_flat_bee() {
    # Create a simple bee with no children for flat clone
    capture_cmd bees create-ticket --ticket-type bee --title "Flat Clone Bee" \
        --hive clone_hive --status pupa --tags '["flat"]' --egg '"flat_egg"'
    local flat_bee
    flat_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees clone --bee-id "$flat_bee"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Clone flat bee" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local written new_id
    written=$(check_json "$CMD_OUT" "d.get('written',0)")
    new_id=$(check_json "$CMD_OUT" "d.get('ticket_id','')")
    if [ "$written" != "1" ]; then
        fail_test "Clone flat bee" "Expected written=1, got $written"
    fi
    if [ "$new_id" = "$flat_bee" ]; then
        fail_test "Clone flat bee" "Cloned ID should differ from source"
    fi
    # Verify content matches
    capture_cmd bees show-ticket --ids "$new_id"
    local clone_title clone_egg
    clone_title=$(check_json "$CMD_OUT" "d['tickets'][0]['title']")
    clone_egg=$(check_json "$CMD_OUT" "d['tickets'][0]['egg']")
    if [ "$clone_title" != "Flat Clone Bee" ]; then
        fail_test "Clone flat bee" "Title mismatch: $clone_title"
    fi
    if [ "$clone_egg" != "flat_egg" ]; then
        fail_test "Clone flat bee" "Egg mismatch: $clone_egg"
    fi
    pass_test "Clone flat bee"
}

test_clone_tree() {
    capture_cmd bees clone --bee-id "$CLONE_BEE"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Clone tree" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local written new_id
    written=$(check_json "$CMD_OUT" "d.get('written',0)")
    new_id=$(check_json "$CMD_OUT" "d.get('ticket_id','')")
    if [ "$written" != "3" ]; then
        fail_test "Clone tree" "Expected written=3, got $written"
    fi
    # Verify cross-refs are remapped
    capture_cmd bees show-ticket --ids "$new_id"
    local new_children
    new_children=$(check_json "$CMD_OUT" "d['tickets'][0].get('children',[])")
    # Children should not contain original IDs
    local has_orig1 has_orig2
    has_orig1=$(check_json "$CMD_OUT" "'$CLONE_TASK1' in (d['tickets'][0].get('children') or [])")
    has_orig2=$(check_json "$CMD_OUT" "'$CLONE_TASK2' in (d['tickets'][0].get('children') or [])")
    if [ "$has_orig1" = "True" ] || [ "$has_orig2" = "True" ]; then
        fail_test "Clone tree" "Cloned root still references original child IDs"
    fi
    pass_test "Clone tree"
}

test_clone_reject_non_bee() {
    capture_cmd bees clone --bee-id "$CLONE_TASK1"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Clone reject non-bee" "Expected failure but got success"
    fi
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    assert_eq "$error_type" "invalid_source_type" "Clone reject non-bee"
}

test_clone_not_found() {
    capture_cmd bees clone --bee-id "b.zzz"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Clone not found" "Expected failure but got success"
    fi
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    assert_eq "$error_type" "bee_not_found" "Clone not found"
}

test_clone_cross_hive() {
    capture_cmd bees colonize-hive \
        --name "Clone Dest" \
        --path "$REPO/tickets/clone_dest"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Clone cross-hive" "Colonize failed: $CMD_OUT"
    fi
    # Create a simple bee to clone
    capture_cmd bees create-ticket --ticket-type bee --title "Cross Hive Src" --hive clone_hive
    local src_bee
    src_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees clone --bee-id "$src_bee" --hive clone_dest
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Clone cross-hive" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local new_id
    new_id=$(check_json "$CMD_OUT" "d.get('ticket_id','')")
    if [ "$new_id" = "$src_bee" ]; then
        fail_test "Clone cross-hive" "Cloned ID should differ"
    fi
    # Verify source still exists in source hive
    capture_cmd bees show-ticket --ids "$src_bee"
    local src_count
    src_count=$(check_json "$CMD_OUT" "len(d.get('tickets',[]))")
    if [ "$src_count" != "1" ]; then
        fail_test "Clone cross-hive" "Source bee should still exist"
    fi
    pass_test "Clone cross-hive"
}

test_clone_incompatible_blocked() {
    # Set restricted status_values on clone_dest
    capture_cmd bees set-status-values --scope hive --hive "Clone Dest" \
        --status-values '["open","done"]'
    # Create bee with status not in dest's allowed values
    capture_cmd bees create-ticket --ticket-type bee --title "Incompat Clone" \
        --hive clone_hive --status pupa
    local incompat_bee
    incompat_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees clone --bee-id "$incompat_bee" --hive clone_dest
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Clone incompatible blocked" "Expected failure but got success"
    fi
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    assert_eq "$error_type" "compatibility_error" "Clone incompatible blocked"
}

test_clone_force_bypass() {
    # Use same incompatible bee
    capture_cmd bees execute-freeform-query \
        --query-yaml "- [type=bee, hive=clone_hive, title~Incompat Clone]"
    local force_bee
    force_bee=$(check_json "$CMD_OUT" "d['ticket_ids'][0]")
    capture_cmd bees clone --bee-id "$force_bee" --hive clone_dest --force
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Clone --force bypass" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local status
    status=$(check_json "$CMD_OUT" "d.get('status','')")
    assert_eq "$status" "success" "Clone --force bypass"
}

run_test test_clone_setup
run_test test_clone_flat_bee
run_test test_clone_tree
run_test test_clone_reject_non_bee
run_test test_clone_not_found
run_test test_clone_cross_hive
run_test test_clone_incompatible_blocked
run_test test_clone_force_bypass

# === FORMER PHASE 5 GROUP B: FAST PARSER PIPELINE ===

test_fast_parser_pipeline() {
    # Self-contained: create hive, tickets, run queries, verify
    capture_cmd bees colonize-hive \
        --name "FP Hive" \
        --path "$REPO/tickets/fp_hive" \
        --child-tiers '{"t1":["Task","Tasks"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Fast parser pipeline" "Colonize failed: $CMD_OUT"
    fi
    # Create bees with distinct statuses
    capture_cmd bees create-ticket --ticket-type bee --title "FP Pupa" --hive fp_hive --status pupa --tags '["shared"]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Fast parser pipeline" "Bee1 creation failed: exit $CMD_EXIT: $CMD_OUT $CMD_ERR"
    fi
    local fp_bee1
    fp_bee1=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type bee --title "FP Worker" --hive fp_hive --status worker --tags '["shared"]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Fast parser pipeline" "Bee2 creation failed: exit $CMD_EXIT: $CMD_OUT $CMD_ERR"
    fi
    local fp_bee2
    fp_bee2=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type bee --title "FP Finished" --hive fp_hive --status finished
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Fast parser pipeline" "Bee3 creation failed: exit $CMD_EXIT: $CMD_OUT $CMD_ERR"
    fi
    # Create a task child
    capture_cmd bees create-ticket --ticket-type t1 --title "FP Task" --hive fp_hive --parent "$fp_bee1"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Fast parser pipeline" "Task creation failed: exit $CMD_EXIT: $CMD_OUT $CMD_ERR"
    fi
    local fp_task
    fp_task=$(check_json "$CMD_OUT" "d['ticket_id']")
    if [ -z "$fp_task" ]; then
        fail_test "Fast parser pipeline" "Task ID empty after creation, CMD_OUT=$CMD_OUT"
    fi

    # Test 1: Filter by type=bee
    capture_cmd bees execute-freeform-query --query-yaml "- [type=bee, hive=fp_hive]"
    local bee_count
    bee_count=$(check_json "$CMD_OUT" "d.get('result_count',0)")
    if [ "$bee_count" != "3" ]; then
        fail_test "Fast parser pipeline" "Type filter: expected 3 bees, got $bee_count"
    fi

    # Test 2: Filter by status=pupa
    capture_cmd bees execute-freeform-query --query-yaml "- [status=pupa, hive=fp_hive]"
    local pupa_count
    pupa_count=$(check_json "$CMD_OUT" "d.get('result_count',0)")
    if [ "$pupa_count" != "1" ]; then
        fail_test "Fast parser pipeline" "Status filter: expected 1 pupa, got $pupa_count"
    fi

    # Test 3: Graph traversal — children of bee1
    capture_cmd bees execute-freeform-query \
        --query-yaml $'- [id='"$fp_bee1"$']\n- [children]'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Fast parser pipeline" "Children query failed: exit $CMD_EXIT: $CMD_OUT $CMD_ERR"
    fi
    local has_task
    has_task=$(check_json "$CMD_OUT" "'$fp_task' in d.get('ticket_ids',[])")
    if [ "$has_task" != "True" ]; then
        fail_test "Fast parser pipeline" "Children traversal: task not found (fp_bee1=$fp_bee1 fp_task=$fp_task ticket_ids=$(check_json "$CMD_OUT" "str(d.get('ticket_ids',[]))" 2>/dev/null || echo '?'))"
    fi

    # Test 4: Chained search + traversal
    capture_cmd bees execute-freeform-query \
        --query-yaml $'- [type=bee, hive=fp_hive]\n- [children]'
    local all_tasks
    all_tasks=$(check_json "$CMD_OUT" "all(not tid.startswith('b.') for tid in d.get('ticket_ids',[]))")
    if [ "$all_tasks" != "True" ]; then
        fail_test "Fast parser pipeline" "Chained query: non-child results found"
    fi

    pass_test "Fast parser pipeline"
}

run_test test_fast_parser_pipeline

# === FORMER PHASE 5 GROUP B: COLONIZE --SCOPE ===

test_colonize_scope_creates_entry() {
    mkdir -p /tmp/scope_test/projects/myrepo
    capture_cmd bees colonize-hive \
        --name "Scoped Hive" \
        --path "$REPO/tickets/scoped_hive" \
        --scope "/tmp/scope_test/projects/**"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Colonize --scope creates entry" "exit $CMD_EXIT: $CMD_OUT"
    fi
    local norm_name
    norm_name=$(check_json "$CMD_OUT" "d.get('normalized_name','')")
    assert_eq "$norm_name" "scoped_hive" "Colonize --scope creates entry"
}

test_colonize_scope_invalid_pattern() {
    capture_cmd bees colonize-hive \
        --name "Bad Hive" \
        --path "$REPO/tickets/bad_hive" \
        --scope "/tmp/*/bad"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Colonize --scope invalid pattern" "Expected failure but got success"
    fi
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    assert_eq "$error_type" "invalid_scope_pattern" "Colonize --scope invalid pattern"
}

run_test test_colonize_scope_creates_entry
run_test test_colonize_scope_invalid_pattern

# === FORMER PHASE 5 GROUP B: SCOPE-AWARE HIVE REGISTRATION ===

test_scope_specificity() {
    mkdir -p "$REPO/tickets/spec_broad_hive" "$REPO/tickets/spec_narrow_hive"
    mkdir -p /tmp/spec_test/projects/active/repo
    mkdir -p /tmp/spec_test/projects/deep/nested/repo

    # Register broad hive
    capture_cmd bees colonize-hive \
        --name "Broad Hive" \
        --path "$REPO/tickets/spec_broad_hive" \
        --scope "/tmp/spec_test/projects/**"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Scope specificity" "Broad colonize failed: $CMD_OUT"
    fi

    # Register narrow hive
    capture_cmd bees colonize-hive \
        --name "Narrow Hive" \
        --path "$REPO/tickets/spec_narrow_hive" \
        --scope "/tmp/spec_test/projects/active/*"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Scope specificity" "Narrow colonize failed: $CMD_OUT"
    fi

    # From narrow match path — narrow wins
    cd /tmp/spec_test/projects/active/repo
    capture_cmd bees list-hives
    local has_narrow has_broad
    has_narrow=$(check_json "$CMD_OUT" "any(h.get('normalized_name')=='narrow_hive' for h in d.get('hives',[]))")
    has_broad=$(check_json "$CMD_OUT" "any(h.get('normalized_name')=='broad_hive' for h in d.get('hives',[]))")
    if [ "$has_narrow" != "True" ]; then
        fail_test "Scope specificity" "Narrow hive not found from narrow path"
    fi
    if [ "$has_broad" = "True" ]; then
        fail_test "Scope specificity" "Broad hive should not appear from narrow path"
    fi

    # From broad-only match path — broad wins
    cd /tmp/spec_test/projects/deep/nested/repo
    capture_cmd bees list-hives
    has_narrow=$(check_json "$CMD_OUT" "any(h.get('normalized_name')=='narrow_hive' for h in d.get('hives',[]))")
    has_broad=$(check_json "$CMD_OUT" "any(h.get('normalized_name')=='broad_hive' for h in d.get('hives',[]))")
    if [ "$has_broad" != "True" ]; then
        fail_test "Scope specificity" "Broad hive not found from broad-only path"
    fi
    if [ "$has_narrow" = "True" ]; then
        fail_test "Scope specificity" "Narrow hive should not appear from broad-only path"
    fi

    cd "$REPO"
    pass_test "Scope specificity"
}

test_scope_duplicate_same_scope() {
    mkdir -p "$REPO/tickets/dup_bugs_a" "$REPO/tickets/dup_bugs_b"
    mkdir -p /tmp/dup_test/repo

    capture_cmd bees colonize-hive \
        --name "Bugs" \
        --path "$REPO/tickets/dup_bugs_a" \
        --scope "/tmp/dup_test/**"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Dup same scope rejected" "First colonize failed: $CMD_OUT"
    fi

    capture_cmd bees colonize-hive \
        --name "Bugs" \
        --path "$REPO/tickets/dup_bugs_b" \
        --scope "/tmp/dup_test/**"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "Dup same scope rejected" "Expected failure but got success"
    fi
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    assert_eq "$error_type" "duplicate_hive_name" "Dup same scope rejected"
}

test_scope_shadow_more_specific() {
    mkdir -p "$REPO/tickets/bugs_broad" "$REPO/tickets/bugs_narrow"
    mkdir -p /tmp/multi_test/general/team/repo
    mkdir -p /tmp/multi_test/general/other/repo

    # Broad Bugs
    capture_cmd bees colonize-hive \
        --name "Bugs" \
        --path "$REPO/tickets/bugs_broad" \
        --scope "/tmp/multi_test/general/**"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Scope shadow more specific" "Broad colonize failed: $CMD_OUT"
    fi

    # Narrow Bugs — should succeed (shadowing)
    capture_cmd bees colonize-hive \
        --name "Bugs" \
        --path "$REPO/tickets/bugs_narrow" \
        --scope "/tmp/multi_test/general/team/*"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "Scope shadow more specific" "Narrow colonize failed: $CMD_OUT"
    fi

    # From narrow path — narrow bugs wins
    cd /tmp/multi_test/general/team/repo
    capture_cmd bees list-hives
    local bugs_path
    bugs_path=$(check_json "$CMD_OUT" "[h.get('path','') for h in d.get('hives',[]) if h.get('normalized_name')=='bugs'][0] if any(h.get('normalized_name')=='bugs' for h in d.get('hives',[])) else ''")
    if ! echo "$bugs_path" | grep -q "bugs_narrow"; then
        fail_test "Scope shadow more specific" "Expected bugs_narrow path from narrow scope, got $bugs_path"
    fi

    # From broad path — broad bugs wins
    cd /tmp/multi_test/general/other/repo
    capture_cmd bees list-hives
    bugs_path=$(check_json "$CMD_OUT" "[h.get('path','') for h in d.get('hives',[]) if h.get('normalized_name')=='bugs'][0] if any(h.get('normalized_name')=='bugs' for h in d.get('hives',[])) else ''")
    if ! echo "$bugs_path" | grep -q "bugs_broad"; then
        fail_test "Scope shadow more specific" "Expected bugs_broad path from broad scope, got $bugs_path"
    fi

    cd "$REPO"
    pass_test "Scope shadow more specific"
}

run_test test_scope_specificity
run_test test_scope_duplicate_same_scope
run_test test_scope_shadow_more_specific

# === FORMER PHASE 5 GROUP B: ID CHARSET AND HIERARCHICAL IDS ===

test_id_charset_rejected() {
    # b.000 contains '0' which is excluded from ID_CHARSET
    capture_cmd bees show-ticket --ids "b.000"
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "ID charset rejected" "Expected failure but got success"
    fi
    local error_type
    error_type=$(check_json "$CMD_OUT" "d.get('error_type','')")
    assert_eq "$error_type" "invalid_ticket_id" "ID charset rejected"
}

test_id_lengths_hierarchy() {
    # Use error_hive which has t1 and t2 tiers
    capture_cmd bees create-ticket --ticket-type bee --title "Len Bee" --hive error_hive
    local len_bee
    len_bee=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t1 --title "Len Task" --hive error_hive --parent "$len_bee"
    local len_task
    len_task=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t2 --title "Len Sub" --hive error_hive --parent "$len_task"
    local len_sub
    len_sub=$(check_json "$CMD_OUT" "d['ticket_id']")

    # Bee: b. + 3 chars = 5 total
    local bee_len=${#len_bee}
    if [ "$bee_len" -ne 5 ]; then
        fail_test "ID lengths hierarchy" "Bee total length: expected 5, got $bee_len ($len_bee)"
    fi
    # T1: t1. + parent_suffix.xx = 9 total (t1. + 3 + . + 2)
    local t1_len=${#len_task}
    if [ "$t1_len" -ne 9 ]; then
        fail_test "ID lengths hierarchy" "T1 total length: expected 9, got $t1_len ($len_task)"
    fi
    # T2: t2. + parent_suffix.xx.yy = 12 total (t2. + 3 + . + 2 + . + 2)
    local t2_len=${#len_sub}
    if [ "$t2_len" -ne 12 ]; then
        fail_test "ID lengths hierarchy" "T2 total length: expected 12, got $t2_len ($len_sub)"
    fi
    pass_test "ID lengths hierarchy"
}

test_id_3level_bidir() {
    # Use the IDs from the previous test — create a fresh set
    capture_cmd bees create-ticket --ticket-type bee --title "Bidir Bee" --hive error_hive
    local b_id
    b_id=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t1 --title "Bidir Task" --hive error_hive --parent "$b_id"
    local t1_id
    t1_id=$(check_json "$CMD_OUT" "d['ticket_id']")
    capture_cmd bees create-ticket --ticket-type t2 --title "Bidir Sub" --hive error_hive --parent "$t1_id"
    local t2_id
    t2_id=$(check_json "$CMD_OUT" "d['ticket_id']")

    # Show all three
    capture_cmd bees show-ticket --ids "$b_id" "$t1_id" "$t2_id"
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "3-level bidir" "Show failed: $CMD_OUT"
    fi
    # Check bee's children contains t1
    local b_has_t1
    b_has_t1=$(check_json "$CMD_OUT" "'$t1_id' in (d['tickets'][0].get('children') or [])")
    if [ "$b_has_t1" != "True" ]; then
        fail_test "3-level bidir" "Bee children missing t1"
    fi
    # Check t1's parent is bee, and children contains t2
    local t1_parent t1_has_t2
    t1_parent=$(check_json "$CMD_OUT" "d['tickets'][1].get('parent','')")
    t1_has_t2=$(check_json "$CMD_OUT" "'$t2_id' in (d['tickets'][1].get('children') or [])")
    if [ "$t1_parent" != "$b_id" ]; then
        fail_test "3-level bidir" "T1 parent should be $b_id, got $t1_parent"
    fi
    if [ "$t1_has_t2" != "True" ]; then
        fail_test "3-level bidir" "T1 children missing t2"
    fi
    # Check t2's parent is t1
    local t2_parent
    t2_parent=$(check_json "$CMD_OUT" "d['tickets'][2].get('parent','')")
    if [ "$t2_parent" != "$t1_id" ]; then
        fail_test "3-level bidir" "T2 parent should be $t1_id, got $t2_parent"
    fi
    pass_test "3-level bidir"
}

run_test test_id_charset_rejected
run_test test_id_lengths_hierarchy
run_test test_id_3level_bidir

# === FORMER PHASE 5 GROUP B: SINGLE TESTS ===

test_list_named_queries_works() {
    # Register a query, list, verify
    capture_cmd bees add-named-query --query-name "test_lnq" --query-yaml "- [type=bee]" --scope global
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "list-named-queries" "add failed: $CMD_OUT"
    fi
    capture_cmd bees list-named-queries
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "list-named-queries" "list failed: $CMD_OUT"
    fi
    local has_query
    has_query=$(check_json "$CMD_OUT" "'test_lnq' in [q['name'] for q in d.get('queries',[])]")
    if [ "$has_query" != "True" ]; then
        fail_test "list-named-queries" "test_lnq not found in list"
    fi
    # Cleanup
    capture_cmd bees delete-named-query --query-name "test_lnq"
    pass_test "list-named-queries"
}

test_t9_cap() {
    # T10 should be rejected
    capture_cmd bees set-types --scope hive --hive "Error Hive" \
        --child-tiers '{"t1":["A","As"],"t2":["B","Bs"],"t3":["C","Cs"],"t4":["D","Ds"],"t5":["E","Es"],"t6":["F","Fs"],"t7":["G","Gs"],"t8":["H","Hs"],"t9":["I","Is"],"t10":["J","Js"]}'
    if [ "$CMD_EXIT" -eq 0 ]; then
        fail_test "T9 cap" "Expected failure for t10 but got success"
    fi
    assert_no_traceback "$CMD_OUT" "T9 cap"
    # T9 should be accepted
    capture_cmd bees set-types --scope hive --hive "Error Hive" \
        --child-tiers '{"t1":["A","As"],"t2":["B","Bs"],"t3":["C","Cs"],"t4":["D","Ds"],"t5":["E","Es"],"t6":["F","Fs"],"t7":["G","Gs"],"t8":["H","Hs"],"t9":["I","Is"]}'
    if [ "$CMD_EXIT" -ne 0 ]; then
        fail_test "T9 cap" "T9 should be accepted: $CMD_OUT"
    fi
    # Restore original tiers
    capture_cmd bees set-types --scope hive --hive "Error Hive" \
        --child-tiers '{"t1":["Task","Tasks"],"t2":["Subtask","Subtasks"]}'
    pass_test "T9 cap"
}

test_http_port_config() {
    # Set http.port in config
    python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.bees' / 'config.json'
d = json.loads(p.read_text())
d['http'] = {'port': 8765}
p.write_text(json.dumps(d))
"
    # Start server in background
    bees serve --http > /tmp/bees_test_server.log 2>&1 &
    local server_pid=$!
    # Give it time to start
    sleep 3
    # Check health on port 8765
    local health_exit=1
    local health_out=""
    health_out=$(curl -sf http://127.0.0.1:8765/health 2>&1) && health_exit=0
    # Kill the server
    kill "$server_pid" 2>/dev/null
    wait "$server_pid" 2>/dev/null || true

    if [ "$health_exit" -ne 0 ]; then
        # Clean up config
        python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.bees' / 'config.json'
d = json.loads(p.read_text())
d.pop('http', None)
p.write_text(json.dumps(d))
"
        fail_test "http.port config" "Server not reachable on port 8765"
    fi

    # Clean up config
    python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.bees' / 'config.json'
d = json.loads(p.read_text())
d.pop('http', None)
p.write_text(json.dumps(d))
"
    pass_test "http.port config"
}

run_test test_list_named_queries_works
run_test test_t9_cap
run_test test_http_port_config

# === SUCCESS SIGNAL ===
echo ""
echo "=========================================="
echo "RELEASE TEST PHASE 2 PASSED"
echo "=========================================="
echo "Tests passed: $PASS_COUNT / $TEST_NUM"
