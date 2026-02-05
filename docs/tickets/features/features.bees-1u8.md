---
id: features.bees-1u8
type: epic
title: Consolidate Create Ticket Test Coverage
description: 'Eliminate 800+ lines of duplicate create ticket tests across 4 files.


  ## Requirements

  - Create `test_mcp_ticket_crud.py` for MCP integration tests

  - Keep `test_ticket_factory.py` for unit tests of factory functions

  - Delete `test_mcp_create_ticket_hive.py`, `test_create_ticket_hive_validation.py`,
  `test_ticket_factory_hive.py`

  - Ensure no duplicate test cases remain


  ## Acceptance Criteria

  - User runs `pytest` - all create ticket tests pass

  - User verifies only 2 files contain create ticket tests (factory unit tests + MCP
  integration)

  - Agent creates PR showing ~800 line reduction with same coverage


  Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md'
labels:
- not-started
up_dependencies:
- features.bees-74p
down_dependencies:
- features.bees-c9p
created_at: '2026-02-05T08:05:46.742728'
updated_at: '2026-02-05T10:35:18.570007'
priority: 2
status: open
bees_version: '1.1'
---

Eliminate 800+ lines of duplicate create ticket tests across 4 files.

## Requirements
- Create `test_mcp_ticket_crud.py` for MCP integration tests
- Keep `test_ticket_factory.py` for unit tests of factory functions
- Delete `test_mcp_create_ticket_hive.py`, `test_create_ticket_hive_validation.py`, `test_ticket_factory_hive.py`
- Ensure no duplicate test cases remain

## Acceptance Criteria
- User runs `pytest` - all create ticket tests pass
- User verifies only 2 files contain create ticket tests (factory unit tests + MCP integration)
- Agent creates PR showing ~800 line reduction with same coverage

Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md
