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
    local suffix="${ID_TASK#t1.}"
    local len=${#suffix}
    if [ "$len" -ne 5 ]; then
        fail_test "Task ID is 5 chars" "Expected 5 chars after t1., got $len ($ID_TASK)"
    fi
    pass_test "Task ID is 5 chars"
}

test_id_subtask_length() {
    local suffix="${ID_SUB#t2.}"
    local len=${#suffix}
    if [ "$len" -ne 7 ]; then
        fail_test "Subtask ID is 7 chars" "Expected 7 chars after t2., got $len ($ID_SUB)"
    fi
    pass_test "Subtask ID is 7 chars"
}

test_id_charset() {
    local valid_re='^[123456789abcdefghijkmnopqrstuvwxyz]+$'
    local bee_suffix="${ID_BEE#b.}"
    local task_suffix="${ID_TASK#t1.}"
    local sub_suffix="${ID_SUB#t2.}"
    if ! echo "$bee_suffix" | grep -qE "$valid_re"; then
        fail_test "ID charset valid" "Bee suffix '$bee_suffix' contains invalid chars"
    fi
    if ! echo "$task_suffix" | grep -qE "$valid_re"; then
        fail_test "ID charset valid" "Task suffix '$task_suffix' contains invalid chars"
    fi
    if ! echo "$sub_suffix" | grep -qE "$valid_re"; then
        fail_test "ID charset valid" "Subtask suffix '$sub_suffix' contains invalid chars"
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

# === Former Phase 5 tests will be appended here ===

# === SUCCESS SIGNAL ===
echo ""
echo "=========================================="
echo "RELEASE TEST PHASE 2 PASSED"
echo "=========================================="
echo "Tests passed: $PASS_COUNT / $TEST_NUM"
