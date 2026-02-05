---
id: features.bees-w0c
type: epic
title: Fix Fragile Mock Patching
description: 'Prevent silent test failures when new modules import `get_repo_root_from_path`.


  ## Requirements

  - Patch `get_repo_root_from_path` at source module only (`src.mcp_repo_utils`)

  - Force reimport of dependent modules in conftest.py

  - Add marker for tests that need real git check: `@pytest.mark.needs_real_git_check`

  - Document the patching approach


  ## Acceptance Criteria

  - User runs `pytest` - all tests pass with centralized mock

  - Agent creates test that imports get_repo_root_from_path in new module - mock still
  applies

  - Agent documents the mock patching pattern in conftest.py


  Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md'
labels:
- not-started
down_dependencies:
- features.bees-c9p
created_at: '2026-02-05T08:05:52.096237'
updated_at: '2026-02-05T10:35:18.553789'
priority: 2
status: open
bees_version: '1.1'
---

Prevent silent test failures when new modules import `get_repo_root_from_path`.

## Requirements
- Patch `get_repo_root_from_path` at source module only (`src.mcp_repo_utils`)
- Force reimport of dependent modules in conftest.py
- Add marker for tests that need real git check: `@pytest.mark.needs_real_git_check`
- Document the patching approach

## Acceptance Criteria
- User runs `pytest` - all tests pass with centralized mock
- Agent creates test that imports get_repo_root_from_path in new module - mock still applies
- Agent documents the mock patching pattern in conftest.py

Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md
