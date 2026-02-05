---
id: features.bees-5at
type: subtask
title: Migrate test_create_ticket.py to use conftest.py fixtures
description: Remove local setup_tickets_dir fixture definition from test_create_ticket.py
  (lines 16-43). Update all test class methods to use single_hive or hive_with_tickets
  fixtures from conftest.py instead. Update function signatures and test setup code
  to reference shared fixtures (bees_repo, single_hive, hive_with_tickets). Ensure
  all test classes (TestCreateEpic, TestCreateTask, TestCreateSubtask, TestBidirectionalRelationships,
  TestValidation, TestEdgeCases) use shared fixtures consistently.
down_dependencies:
- features.bees-cdn
- features.bees-eo5
parent: features.bees-oxx
created_at: '2026-02-05T12:05:37.421105'
updated_at: '2026-02-05T12:11:22.944102'
status: completed
bees_version: '1.1'
---

Remove local setup_tickets_dir fixture definition from test_create_ticket.py (lines 16-43). Update all test class methods to use single_hive or hive_with_tickets fixtures from conftest.py instead. Update function signatures and test setup code to reference shared fixtures (bees_repo, single_hive, hive_with_tickets). Ensure all test classes (TestCreateEpic, TestCreateTask, TestCreateSubtask, TestBidirectionalRelationships, TestValidation, TestEdgeCases) use shared fixtures consistently.
