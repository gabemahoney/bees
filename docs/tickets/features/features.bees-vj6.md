---
id: features.bees-vj6
type: subtask
title: Migrate test_mcp_server.py to conftest fixtures
description: 'Review test file for any local setup fixtures. Replace with bees_repo,
  single_hive, multi_hive, or mock_mcp_context as appropriate. Update test signatures.
  Verify all server lifecycle and health check tests pass.


  Context: Part of test fixture migration epic to eliminate 500+ lines of duplicate
  fixtures.


  Files: tests/test_mcp_server.py


  Acceptance: Tests pass with pytest. No local setup_* fixtures remain.'
down_dependencies:
- features.bees-v4c
parent: features.bees-xo8
created_at: '2026-02-05T12:05:51.535489'
updated_at: '2026-02-05T12:28:13.556549'
status: completed
bees_version: '1.1'
---

Review test file for any local setup fixtures. Replace with bees_repo, single_hive, multi_hive, or mock_mcp_context as appropriate. Update test signatures. Verify all server lifecycle and health check tests pass.

Context: Part of test fixture migration epic to eliminate 500+ lines of duplicate fixtures.

Files: tests/test_mcp_server.py

Acceptance: Tests pass with pytest. No local setup_* fixtures remain.
