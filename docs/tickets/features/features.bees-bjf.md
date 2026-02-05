---
id: features.bees-bjf
type: subtask
title: Create integration test for bidirectional sync in hive_with_tickets
description: 'Add integration test in tests/integration/ that:

  - Uses hive_with_tickets fixture

  - Verifies Epic''s children array includes Task ID

  - Verifies Task''s children array includes Subtask ID

  - Verifies parent fields are correctly set

  - Tests that MCP functions (_create_ticket, _update_ticket) properly sync bidirectional
  relationships


  Context: conftest.py hive_with_tickets fixture (lines 847-893) creates parent→child
  links but doesn''t populate children arrays. This test verifies MCP functions handle
  bidirectional sync correctly.


  Files: Create tests/integration/test_bidirectional_sync.py


  Acceptance: Test passes, verifies children arrays are populated when using MCP functions
  vs raw ticket creation'
down_dependencies:
- features.bees-dst
- features.bees-kuc
- features.bees-p0d
parent: features.bees-ho6
created_at: '2026-02-05T09:43:36.151656'
updated_at: '2026-02-05T10:01:26.667355'
status: completed
bees_version: '1.1'
---

Add integration test in tests/integration/ that:
- Uses hive_with_tickets fixture
- Verifies Epic's children array includes Task ID
- Verifies Task's children array includes Subtask ID
- Verifies parent fields are correctly set
- Tests that MCP functions (_create_ticket, _update_ticket) properly sync bidirectional relationships

Context: conftest.py hive_with_tickets fixture (lines 847-893) creates parent→child links but doesn't populate children arrays. This test verifies MCP functions handle bidirectional sync correctly.

Files: Create tests/integration/test_bidirectional_sync.py

Acceptance: Test passes, verifies children arrays are populated when using MCP functions vs raw ticket creation
