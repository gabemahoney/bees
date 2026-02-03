---
id: features.bees-f2n
type: subtask
title: Add unit tests for get_repo_root() error behavior
description: 'Add tests to verify get_repo_root() raises ValueError when it cannot
  determine repo_root, confirming that it never returns None.


  Test cases:

  - Test with no context and invalid cwd path

  - Test with context but no roots protocol support and no repo_root parameter

  - Verify ValueError is raised in both cases

  - Verify error messages are descriptive


  This validates our refactoring decision to remove the dead code checks.'
labels:
- testing
- implementation
down_dependencies:
- features.bees-407
parent: features.bees-yp9
created_at: '2026-02-03T12:42:41.417328'
updated_at: '2026-02-03T12:48:43.605591'
status: completed
bees_version: '1.1'
---

Add tests to verify get_repo_root() raises ValueError when it cannot determine repo_root, confirming that it never returns None.

Test cases:
- Test with no context and invalid cwd path
- Test with context but no roots protocol support and no repo_root parameter
- Verify ValueError is raised in both cases
- Verify error messages are descriptive

This validates our refactoring decision to remove the dead code checks.
