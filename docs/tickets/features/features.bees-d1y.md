---
id: features.bees-d1y
type: subtask
title: Add test for _sanitize_hive with explicit repo_root parameter
description: 'Add test_sanitize_hive_with_explicit_repo_root() to tests/test_mcp_roots.py
  that verifies _sanitize_hive accepts and uses the explicit repo_root parameter when
  ctx=None.


  Context: _sanitize_hive was modified to accept repo_root parameter but lacks test
  coverage.


  Requirements:

  - Test should call _sanitize_hive with repo_root=str(test_repo) and ctx=None

  - Should verify repo_root is used by attempting to sanitize a nonexistent hive

  - Should validate the appropriate error is raised (hive not found)


  Acceptance: Test passes and validates repo_root parameter works for _sanitize_hive.'
down_dependencies:
- features.bees-qio
parent: features.bees-v4d
created_at: '2026-02-03T12:43:10.681507'
updated_at: '2026-02-03T13:02:15.423286'
status: completed
bees_version: '1.1'
---

Add test_sanitize_hive_with_explicit_repo_root() to tests/test_mcp_roots.py that verifies _sanitize_hive accepts and uses the explicit repo_root parameter when ctx=None.

Context: _sanitize_hive was modified to accept repo_root parameter but lacks test coverage.

Requirements:
- Test should call _sanitize_hive with repo_root=str(test_repo) and ctx=None
- Should verify repo_root is used by attempting to sanitize a nonexistent hive
- Should validate the appropriate error is raised (hive not found)

Acceptance: Test passes and validates repo_root parameter works for _sanitize_hive.
