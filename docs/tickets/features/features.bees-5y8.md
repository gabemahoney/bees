---
id: features.bees-5y8
type: epic
title: Split Monolithic MCP Server Tests
description: 'Improve test maintainability by splitting 3,159-line file into focused
  modules.


  ## Requirements

  - Create `test_mcp_server_lifecycle.py` (~400 lines) - server startup/shutdown/tool
  registration

  - Create `test_mcp_scan_validate.py` (~300 lines) - scan and validation tests

  - Keep `test_mcp_server.py` (~1,600 lines) - remaining tool tests

  - Ensure all 155 tests are preserved


  ## Acceptance Criteria

  - User runs `pytest tests/test_mcp_*.py` - all 155 tests pass

  - User verifies no single test file exceeds 1,600 lines

  - Agent creates PR showing file split with no lost tests


  Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md'
labels:
- not-started
up_dependencies:
- features.bees-74p
created_at: '2026-02-05T08:05:49.511857'
updated_at: '2026-02-05T08:05:57.824710'
priority: 2
status: open
bees_version: '1.1'
---

Improve test maintainability by splitting 3,159-line file into focused modules.

## Requirements
- Create `test_mcp_server_lifecycle.py` (~400 lines) - server startup/shutdown/tool registration
- Create `test_mcp_scan_validate.py` (~300 lines) - scan and validation tests
- Keep `test_mcp_server.py` (~1,600 lines) - remaining tool tests
- Ensure all 155 tests are preserved

## Acceptance Criteria
- User runs `pytest tests/test_mcp_*.py` - all 155 tests pass
- User verifies no single test file exceeds 1,600 lines
- Agent creates PR showing file split with no lost tests

Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md
