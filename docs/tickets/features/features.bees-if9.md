---
id: features.bees-if9
type: subtask
title: Add test for _abandon_hive with explicit repo_root parameter
description: 'Add test_abandon_hive_with_explicit_repo_root() to tests/test_mcp_roots.py
  that verifies _abandon_hive accepts and uses the explicit repo_root parameter when
  ctx=None.


  Context: _abandon_hive was modified to accept repo_root parameter but lacks test
  coverage.


  Requirements:

  - Test should call _abandon_hive with repo_root=str(test_repo) and ctx=None

  - Should verify repo_root is used by attempting to abandon a nonexistent hive

  - Should validate the appropriate error is raised (hive not found)


  Acceptance: Test passes and validates repo_root parameter works for _abandon_hive.'
parent: features.bees-v4d
created_at: '2026-02-03T12:43:01.976612'
updated_at: '2026-02-03T13:02:14.230874'
status: completed
bees_version: '1.1'
---

Add test_abandon_hive_with_explicit_repo_root() to tests/test_mcp_roots.py that verifies _abandon_hive accepts and uses the explicit repo_root parameter when ctx=None.

Context: _abandon_hive was modified to accept repo_root parameter but lacks test coverage.

Requirements:
- Test should call _abandon_hive with repo_root=str(test_repo) and ctx=None
- Should verify repo_root is used by attempting to abandon a nonexistent hive
- Should validate the appropriate error is raised (hive not found)

Acceptance: Test passes and validates repo_root parameter works for _abandon_hive.
