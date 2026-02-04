---
id: features.bees-41y
type: subtask
title: Add unit tests for conftest fixture patching behavior
description: '**Context**: After modifying conftest.py patching logic, ensure the
  mocking behavior is properly tested.


  **Requirements**:

  - Create or update tests that verify mock_git_repo_check fixture properly patches
  get_repo_root_from_path

  - Test that the mock allows tests to run in non-git temporary directories

  - Test that @pytest.mark.needs_real_git_check bypasses the mock when needed

  - Test edge cases: nested directories, missing .git/.bees, falling back to cwd

  - Verify that both mcp_repo_utils and mcp_server (if still patched) use the mock
  correctly


  **Files**: tests/test_conftest.py (or appropriate test file)


  **Parent Task**: features.bees-l4c


  **Acceptance**: Comprehensive unit tests verify fixture patching behavior works
  correctly.'
up_dependencies:
- features.bees-e6m
down_dependencies:
- features.bees-xaa
parent: features.bees-l4c
created_at: '2026-02-03T19:27:24.346539'
updated_at: '2026-02-03T19:29:54.684124'
status: completed
bees_version: '1.1'
---

**Context**: After modifying conftest.py patching logic, ensure the mocking behavior is properly tested.

**Requirements**:
- Create or update tests that verify mock_git_repo_check fixture properly patches get_repo_root_from_path
- Test that the mock allows tests to run in non-git temporary directories
- Test that @pytest.mark.needs_real_git_check bypasses the mock when needed
- Test edge cases: nested directories, missing .git/.bees, falling back to cwd
- Verify that both mcp_repo_utils and mcp_server (if still patched) use the mock correctly

**Files**: tests/test_conftest.py (or appropriate test file)

**Parent Task**: features.bees-l4c

**Acceptance**: Comprehensive unit tests verify fixture patching behavior works correctly.
