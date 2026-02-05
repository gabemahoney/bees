---
id: features.bees-kta
type: subtask
title: Migrate test_delete_ticket.py to use conftest.py fixtures
description: Remove local setup_tickets_dir fixture definition from test_delete_ticket.py
  (lines 16-43). Remove local setup_multi_hive fixture (lines 447-482). Update all
  test class methods to use single_hive or multi_hive fixtures from conftest.py instead.
  Update function signatures in TestDeleteTicketBasic, TestDeleteTicketParentCleanup,
  TestDeleteTicketDependencyCleanup, TestDeleteTicketCascade, TestDeleteTicketEdgeCases,
  and TestDeleteTicketHiveRouting to reference shared fixtures consistently.
down_dependencies:
- features.bees-cdn
- features.bees-eo5
parent: features.bees-oxx
created_at: '2026-02-05T12:05:40.880335'
updated_at: '2026-02-05T12:14:26.939225'
status: completed
bees_version: '1.1'
---

Remove local setup_tickets_dir fixture definition from test_delete_ticket.py (lines 16-43). Remove local setup_multi_hive fixture (lines 447-482). Update all test class methods to use single_hive or multi_hive fixtures from conftest.py instead. Update function signatures in TestDeleteTicketBasic, TestDeleteTicketParentCleanup, TestDeleteTicketDependencyCleanup, TestDeleteTicketCascade, TestDeleteTicketEdgeCases, and TestDeleteTicketHiveRouting to reference shared fixtures consistently.
