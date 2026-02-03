---
id: features.bees-g2e
type: subtask
title: Add test for _rename_hive with explicit repo_root parameter
description: 'Add test_rename_hive_with_explicit_repo_root() to tests/test_mcp_roots.py
  that verifies _rename_hive accepts and uses the explicit repo_root parameter when
  ctx=None.


  Context: _rename_hive was modified to accept repo_root parameter but lacks test
  coverage.


  Requirements:

  - Test should call _rename_hive with repo_root=str(test_repo) and ctx=None

  - Should verify repo_root is used by attempting to rename a nonexistent hive

  - Should validate the appropriate error is raised (hive not found)


  Acceptance: Test passes and validates repo_root parameter works for _rename_hive.'
parent: features.bees-v4d
created_at: '2026-02-03T12:43:06.471664'
updated_at: '2026-02-03T13:02:14.850668'
status: completed
bees_version: '1.1'
---

Add test_rename_hive_with_explicit_repo_root() to tests/test_mcp_roots.py that verifies _rename_hive accepts and uses the explicit repo_root parameter when ctx=None.

Context: _rename_hive was modified to accept repo_root parameter but lacks test coverage.

Requirements:
- Test should call _rename_hive with repo_root=str(test_repo) and ctx=None
- Should verify repo_root is used by attempting to rename a nonexistent hive
- Should validate the appropriate error is raised (hive not found)

Acceptance: Test passes and validates repo_root parameter works for _rename_hive.
