---
id: features.bees-cdn
type: subtask
title: Verify codebase has no remaining local fixture definitions
description: Search codebase for 'def setup_tickets_dir' and verify no results found
  in test_create_ticket.py and test_delete_ticket.py. Search for 'def setup_multi_hive'
  and verify removal from test_delete_ticket.py. Confirm all tests in these files
  reference conftest.py fixtures only.
up_dependencies:
- features.bees-5at
- features.bees-kta
parent: features.bees-oxx
created_at: '2026-02-05T12:05:48.627922'
updated_at: '2026-02-05T12:14:48.379454'
status: completed
bees_version: '1.1'
---

Search codebase for 'def setup_tickets_dir' and verify no results found in test_create_ticket.py and test_delete_ticket.py. Search for 'def setup_multi_hive' and verify removal from test_delete_ticket.py. Confirm all tests in these files reference conftest.py fixtures only.
