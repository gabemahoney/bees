---
id: features.bees-74p
type: epic
title: Migrate Tests to Shared Fixtures
description: "Eliminate 500+ lines of duplicate fixture definitions across 10 test\
  \ files.\n\n## Requirements\n- Migrate 10 test files from local fixtures to conftest.py\
  \ fixtures:\n  - test_create_ticket.py, test_delete_ticket.py, test_mcp_create_ticket_hive.py\n\
  \  - test_create_ticket_hive_validation.py, test_mcp_server.py, test_paths.py\n\
  \  - test_ticket_factory_hive.py, test_pipeline.py, test_generate_demo_tickets.py\n\
  \  - test_mcp_rename_hive.py\n- Delete all local fixture definitions\n- Update test\
  \ signatures and bodies to use shared fixtures\n\n## Acceptance Criteria\n- User\
  \ runs `pytest` - all tests pass\n- User searches codebase for \"def setup_tickets_dir\"\
  \ - no results found\n- Agent creates PR showing ~500 line reduction\n\nSource:\
  \ /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md"
up_dependencies:
- features.bees-y6w
down_dependencies:
- features.bees-1u8
- features.bees-5y8
- features.bees-c9p
children:
- features.bees-oxx
- features.bees-xo8
- features.bees-4vi
created_at: '2026-02-05T08:05:44.016743'
updated_at: '2026-02-05T12:39:34.105286'
priority: 2
status: completed
bees_version: '1.1'
---

Eliminate 500+ lines of duplicate fixture definitions across 10 test files.

## Requirements
- Migrate 10 test files from local fixtures to conftest.py fixtures:
  - test_create_ticket.py, test_delete_ticket.py, test_mcp_create_ticket_hive.py
  - test_create_ticket_hive_validation.py, test_mcp_server.py, test_paths.py
  - test_ticket_factory_hive.py, test_pipeline.py, test_generate_demo_tickets.py
  - test_mcp_rename_hive.py
- Delete all local fixture definitions
- Update test signatures and bodies to use shared fixtures

## Acceptance Criteria
- User runs `pytest` - all tests pass
- User searches codebase for "def setup_tickets_dir" - no results found
- Agent creates PR showing ~500 line reduction

Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md
