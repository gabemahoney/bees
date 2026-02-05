---
id: features.bees-yus
type: subtask
title: Migrate test_mcp_rename_hive.py to conftest fixtures
description: 'Replace temp_hive_setup fixture with multi_hive from conftest.py. Remove
  local fixture definition. Update all test signatures to use shared fixtures. Verify
  rename operations still work correctly.


  Context: Part of test fixture migration epic to eliminate 500+ lines of duplicate
  fixtures.


  Files: tests/test_mcp_rename_hive.py


  Acceptance: Tests pass with pytest. Local temp_hive_setup fixture deleted.'
down_dependencies:
- features.bees-v4c
parent: features.bees-xo8
created_at: '2026-02-05T12:05:53.753903'
updated_at: '2026-02-05T12:28:45.611397'
status: completed
bees_version: '1.1'
---

Replace temp_hive_setup fixture with multi_hive from conftest.py. Remove local fixture definition. Update all test signatures to use shared fixtures. Verify rename operations still work correctly.

Context: Part of test fixture migration epic to eliminate 500+ lines of duplicate fixtures.

Files: tests/test_mcp_rename_hive.py

Acceptance: Tests pass with pytest. Local temp_hive_setup fixture deleted.
