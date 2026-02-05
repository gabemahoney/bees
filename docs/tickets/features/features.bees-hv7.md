---
id: features.bees-hv7
type: subtask
title: Migrate test_mcp_create_ticket_hive.py to conftest fixtures
description: 'Replace temp_tickets_dir fixture with single_hive or multi_hive from
  conftest.py. Remove local fixture definition (~110 lines). Update all test signatures.
  Verify tests pass.


  Context: Part of test fixture migration epic to eliminate 500+ lines of duplicate
  fixtures.


  Files: tests/test_mcp_create_ticket_hive.py


  Acceptance: Tests pass with pytest. Local temp_tickets_dir fixture deleted.'
down_dependencies:
- features.bees-v4c
parent: features.bees-xo8
created_at: '2026-02-05T12:05:46.001602'
updated_at: '2026-02-05T12:25:04.232407'
status: completed
bees_version: '1.1'
---

Replace temp_tickets_dir fixture with single_hive or multi_hive from conftest.py. Remove local fixture definition (~110 lines). Update all test signatures. Verify tests pass.

Context: Part of test fixture migration epic to eliminate 500+ lines of duplicate fixtures.

Files: tests/test_mcp_create_ticket_hive.py

Acceptance: Tests pass with pytest. Local temp_tickets_dir fixture deleted.
