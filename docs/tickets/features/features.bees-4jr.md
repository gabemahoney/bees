---
id: features.bees-4jr
type: subtask
title: Migrate test_create_ticket_hive_validation.py to conftest fixtures
description: 'Replace temp_hive_setup fixture with single_hive or multi_hive from
  conftest.py. Remove local fixture definition. Update all test signatures. Verify
  tests pass.


  Context: Part of test fixture migration epic to eliminate 500+ lines of duplicate
  fixtures.


  Files: tests/test_create_ticket_hive_validation.py


  Acceptance: Tests pass with pytest. Local temp_hive_setup fixture deleted.'
down_dependencies:
- features.bees-v4c
parent: features.bees-xo8
created_at: '2026-02-05T12:05:48.131595'
updated_at: '2026-02-05T12:26:58.166204'
status: completed
bees_version: '1.1'
---

Replace temp_hive_setup fixture with single_hive or multi_hive from conftest.py. Remove local fixture definition. Update all test signatures. Verify tests pass.

Context: Part of test fixture migration epic to eliminate 500+ lines of duplicate fixtures.

Files: tests/test_create_ticket_hive_validation.py

Acceptance: Tests pass with pytest. Local temp_hive_setup fixture deleted.
