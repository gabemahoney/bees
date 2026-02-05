---
id: features.bees-pgf
type: task
title: Investigate and resolve skipped tests
description: |
  Investigate all 54 skipped tests and either fix them or remove them if they're obsolete.
  
  **Breakdown of skipped tests:**
  
  1. **test_pipeline.py** (9 tests) - Marked with "tickets_dir parameter is deprecated - PipelineEvaluator now loads from hive config"
     - Decision needed: Are these testing deprecated functionality that should be removed, or should they be updated for hive-based config?
  
  2. **test_query_tools.py** (~16 tests) - Marked with "Tests need update for hive-based config system"
     - Need to update tests to work with hive-based configuration
     - Tests in TestExecuteQueryTool and TestExecuteFreeformQuery classes
  
  3. **test_multi_hive_query.py** (7 tests) - Marked with "Tests need update for hive-based config system"
     - All in TestPipelineHiveFiltering class
     - Need to update for hive-based configuration
  
  4. **test_sample_tickets.py** (13 tests) - Runtime skip when sample ticket files don't exist
     - Decision needed: Should we create sample tickets, or remove these tests?
     - Tests check sample-epic.md, sample-task.md, sample-subtask.md in tickets/ directory
  
  5. **test_mcp_hive_utils.py** (1 test) - test_scan_for_hive_updates_config_on_recovery
     - Marked "scan_for_hive doesn't auto-update config - known limitation"
     - Decision needed: Is this a feature we want, or should test be removed?
  
  6. **test_mcp_server.py** (1 test) - test_tool_registration_count
     - Marked "Tool names have '- ' prefix issue - known issue with FastMCP tool naming"
     - Decision needed: Fix the tool naming issue or remove test?
  
  **Goals:**
  - Review each category of skipped tests
  - Fix tests that should be working
  - Remove tests that are obsolete/testing deprecated functionality
  - Document any intentional skips with clear reasons
  - Aim for 0 skipped tests or only legitimate skips with good documentation
parent: features.bees-nho
children: ["features.bees-pgf1", "features.bees-pgf2", "features.bees-pgf3", "features.bees-pgf4", "features.bees-pgf5", "features.bees-pgf6"]
status: completed
priority: 2
labels: ["tests", "tech-debt"]
created_at: '2026-02-05T05:30:00.000000'
updated_at: '2026-02-05T05:30:00.000000'
bees_version: '1.1'
---

# Investigation Plan

## 1. Deprecated tickets_dir Tests (test_pipeline.py)

These tests check functionality for passing `tickets_dir` parameter directly to PipelineEvaluator. Since we now use hive-based config, decide:
- **Option A**: Remove tests completely (functionality is deprecated)
- **Option B**: Update tests to use hive-based approach

**Recommendation**: Remove tests - the functionality they test is deprecated and replaced by hive config system.

## 2. Hive-Based Config Updates (test_query_tools.py, test_multi_hive_query.py)

These tests were skipped because they need updating for the hive-based config system. They should be fixed because:
- Query functionality is actively used
- Multi-hive filtering is a core feature
- These are integration tests for important functionality

**Recommendation**: Fix these tests by updating fixtures to use hive config.

## 3. Sample Ticket Tests (test_sample_tickets.py)

Tests expect sample ticket files to exist in tickets/epics/, tickets/tasks/, tickets/subtasks/.

**Recommendation**: Determine if sample tickets are part of the repo spec. If yes, create them. If no, remove these tests.

## 4. Known Limitations

- **scan_for_hive auto-update**: If this is truly a limitation we accept, document it better and keep skip
- **Tool naming issue**: If this is a FastMCP bug we can't control, keep skip with better docs

## Success Criteria

- All tests either passing or removed
- Any remaining skips have clear, justified reasons
- No obsolete test code remaining
- Documentation updated if behavior changed
