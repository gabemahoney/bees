---
id: features.bees-h95
type: subtask
title: Update README.md with conftest.py patching strategy documentation
description: '**Context**: After clarifying the patching approach in conftest.py,
  document the testing strategy for future reference.


  **Requirements**:

  - Add or update section in README.md explaining how the test suite mocks git repository
  validation

  - Document that tests patch mcp_repo_utils.get_repo_root_from_path to allow tests
  in non-git temp directories

  - Mention the @pytest.mark.needs_real_git_check marker for tests that require actual
  git validation

  - Keep documentation concise and focused on usage


  **Files**: README.md


  **Parent Task**: features.bees-l4c


  **Acceptance**: README.md clearly documents the test mocking strategy for git repo
  validation.'
up_dependencies:
- features.bees-e6m
parent: features.bees-l4c
created_at: '2026-02-03T19:27:11.331927'
updated_at: '2026-02-03T19:29:04.530750'
status: completed
bees_version: '1.1'
---

**Context**: After clarifying the patching approach in conftest.py, document the testing strategy for future reference.

**Requirements**:
- Add or update section in README.md explaining how the test suite mocks git repository validation
- Document that tests patch mcp_repo_utils.get_repo_root_from_path to allow tests in non-git temp directories
- Mention the @pytest.mark.needs_real_git_check marker for tests that require actual git validation
- Keep documentation concise and focused on usage

**Files**: README.md

**Parent Task**: features.bees-l4c

**Acceptance**: README.md clearly documents the test mocking strategy for git repo validation.
