---
id: features.bees-s0g
type: task
title: Update test assertions for changed repo_root behavior
description: 'The Epic changed colonize_hive and repo_root validation behavior. 23
  tests in test_mcp_roots.py and test_mcp_server.py now fail because they expect the
  old behavior.


  Failing tests:

  - test_mcp_roots.py: test_colonize_hive_uses_context, test_colonize_hive_with_explicit_repo_root
  (2 tests)

  - test_mcp_server.py: TestGetRepoRoot, TestValidateHivePath, TestColonizeHiveMCPIntegration,
  TestColonizeHiveMCPUnit, TestAbandonHive (21 tests)


  Example: test_colonize_hive_uses_context expects error but gets success. Log shows
  "colonize_hive: Hive path outside repo root, using hive path" - behavior changed
  from failing to warning.


  What Needs to Change:

  - Update test assertions to match new validation behavior

  - Fix tests that expect errors where we now succeed with warnings

  - Update mocked function signatures to include new repo_root parameters

  - Achieve 100% test pass rate


  Final blocker for Epic completion.'
labels:
- bug
parent: features.bees-h0a
created_at: '2026-02-03T14:43:20.503023'
updated_at: '2026-02-03T15:45:44.206784'
priority: 1
status: completed
bees_version: '1.1'
---

The Epic changed colonize_hive and repo_root validation behavior. 23 tests in test_mcp_roots.py and test_mcp_server.py now fail because they expect the old behavior.

Failing tests:
- test_mcp_roots.py: test_colonize_hive_uses_context, test_colonize_hive_with_explicit_repo_root (2 tests)
- test_mcp_server.py: TestGetRepoRoot, TestValidateHivePath, TestColonizeHiveMCPIntegration, TestColonizeHiveMCPUnit, TestAbandonHive (21 tests)

Example: test_colonize_hive_uses_context expects error but gets success. Log shows "colonize_hive: Hive path outside repo root, using hive path" - behavior changed from failing to warning.

What Needs to Change:
- Update test assertions to match new validation behavior
- Fix tests that expect errors where we now succeed with warnings
- Update mocked function signatures to include new repo_root parameters
- Achieve 100% test pass rate

Final blocker for Epic completion.
