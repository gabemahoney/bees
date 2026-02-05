---
id: features.bees-2ws
type: subtask
title: Add unit tests for fixture migration verification
description: 'Add tests to verify no local fixture definitions exist in migrated test
  files (test_paths.py, test_ticket_factory_hive.py, test_pipeline.py, test_generate_demo_tickets.py).
  Test that all fixtures come from conftest.py. Test edge cases for fixture usage
  patterns.


  **Context**: Part of Task features.bees-4vi migrating utility and factory tests
  to shared fixtures.


  **Files**: New test file or addition to existing test suite


  **Acceptance**: Tests verify no local fixtures in migrated files, all tests pass.'
up_dependencies:
- features.bees-92k
down_dependencies:
- features.bees-qs0
parent: features.bees-4vi
created_at: '2026-02-05T12:05:54.392198'
updated_at: '2026-02-05T12:38:10.218075'
status: completed
bees_version: '1.1'
---

Add tests to verify no local fixture definitions exist in migrated test files (test_paths.py, test_ticket_factory_hive.py, test_pipeline.py, test_generate_demo_tickets.py). Test that all fixtures come from conftest.py. Test edge cases for fixture usage patterns.

**Context**: Part of Task features.bees-4vi migrating utility and factory tests to shared fixtures.

**Files**: New test file or addition to existing test suite

**Acceptance**: Tests verify no local fixtures in migrated files, all tests pass.
