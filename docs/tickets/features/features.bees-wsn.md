---
id: features.bees-wsn
type: subtask
title: Add @pytest.mark.needs_real_git_check marker to tests requiring real git behavior
description: 'Context: Some tests need to verify actual git repository detection logic
  and should not use the centralized mock.


  Review Conducted:

  - Checked all test files for functions that test get_repo_root_from_path() itself

  - Verified marker usage in test_mcp_repo_utils.py

  - Verified marker usage in test_conftest.py


  Findings:

  - test_mcp_repo_utils.py already has @pytest.mark.needs_real_git_check on lines
  11, 24, 35, 47, 230, 257

  - test_conftest.py already has @pytest.mark.needs_real_git_check on lines 101, 115

  - These tests correctly bypass the centralized mock and use real git repository
  detection

  - No additional markers needed


  Tests Marked:

  - test_get_repo_root_from_path_finds_git_repo()

  - test_get_repo_root_from_path_from_repo_root()

  - test_get_repo_root_from_path_raises_on_non_git()

  - test_get_repo_root_from_path_walks_up_tree()

  - test_get_repo_root_falls_back_to_cwd_when_no_context()

  - test_get_repo_root_with_invalid_git_path_in_context()

  - test_marker_bypasses_mock_uses_real_git()

  - test_marker_bypasses_mock_fails_in_non_git()


  All tests pass (1316 passed, 2 skipped)'
down_dependencies:
- features.bees-o3k
parent: features.bees-tv7
created_at: '2026-02-05T12:46:07.934692'
updated_at: '2026-02-05T16:05:36.202555'
status: completed
bees_version: '1.1'
---

Context: Some tests need to verify actual git repository detection logic and should not use the centralized mock.

Review Conducted:
- Checked all test files for functions that test get_repo_root_from_path() itself
- Verified marker usage in test_mcp_repo_utils.py
- Verified marker usage in test_conftest.py

Findings:
- test_mcp_repo_utils.py already has @pytest.mark.needs_real_git_check on lines 11, 24, 35, 47, 230, 257
- test_conftest.py already has @pytest.mark.needs_real_git_check on lines 101, 115
- These tests correctly bypass the centralized mock and use real git repository detection
- No additional markers needed

Tests Marked:
- test_get_repo_root_from_path_finds_git_repo()
- test_get_repo_root_from_path_from_repo_root()
- test_get_repo_root_from_path_raises_on_non_git()
- test_get_repo_root_from_path_walks_up_tree()
- test_get_repo_root_falls_back_to_cwd_when_no_context()
- test_get_repo_root_with_invalid_git_path_in_context()
- test_marker_bypasses_mock_uses_real_git()
- test_marker_bypasses_mock_fails_in_non_git()

All tests pass (1316 passed, 2 skipped)
