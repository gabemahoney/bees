---
id: features.bees-oxx
type: task
title: Migrate Core Ticket Operation Tests
description: 'Migrate test_create_ticket.py and test_delete_ticket.py to use conftest.py
  fixtures. Remove local fixture definitions (setup_tickets_dir, etc.). Update test
  function signatures to reference shared fixtures (bees_repo, single_hive, hive_with_tickets).
  Verify all tests pass after migration. Files: tests/test_create_ticket.py, tests/test_delete_ticket.py.
  Epic: features.bees-74p'
parent: features.bees-74p
children:
- features.bees-5at
- features.bees-kta
- features.bees-cdn
- features.bees-eo5
created_at: '2026-02-05T12:05:00.171222'
updated_at: '2026-02-05T12:15:49.463999'
priority: 0
status: completed
bees_version: '1.1'
---

Migrate test_create_ticket.py and test_delete_ticket.py to use conftest.py fixtures. Remove local fixture definitions (setup_tickets_dir, etc.). Update test function signatures to reference shared fixtures (bees_repo, single_hive, hive_with_tickets). Verify all tests pass after migration. Files: tests/test_create_ticket.py, tests/test_delete_ticket.py. Epic: features.bees-74p
