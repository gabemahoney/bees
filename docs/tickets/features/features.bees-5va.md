---
id: features.bees-5va
type: epic
title: Remove Legacy Skipped Tests
description: 'Eliminate dead code that confuses developers and inflates codebase size.


  ## Requirements

  - Delete `test_writer.py` (589 lines, entirely skipped)

  - Verify functionality is covered by `test_ticket_factory.py`, `test_reader.py`,
  and MCP integration tests

  - Ensure no unique test cases are lost


  ## Acceptance Criteria

  - User runs `pytest` - all tests pass, no skipped test files

  - User checks coverage with `pytest --cov=src` - coverage remains unchanged

  - test_writer.py no longer exists in tests directory


  Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md'
down_dependencies:
- features.bees-c9p
children:
- features.bees-nkt
- features.bees-uwi
- features.bees-y9a
- features.bees-h77
- features.bees-qon
- features.bees-ho6
- features.bees-raw
- features.bees-9e9
created_at: '2026-02-05T08:05:35.529263'
updated_at: '2026-02-05T10:35:18.562362'
priority: 2
status: completed
bees_version: '1.1'
---

Eliminate dead code that confuses developers and inflates codebase size.

## Requirements
- Delete `test_writer.py` (589 lines, entirely skipped)
- Verify functionality is covered by `test_ticket_factory.py`, `test_reader.py`, and MCP integration tests
- Ensure no unique test cases are lost

## Acceptance Criteria
- User runs `pytest` - all tests pass, no skipped test files
- User checks coverage with `pytest --cov=src` - coverage remains unchanged
- test_writer.py no longer exists in tests directory

Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md
