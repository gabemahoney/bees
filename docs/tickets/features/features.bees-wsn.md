---
id: features.bees-wsn
type: subtask
title: Add @pytest.mark.needs_real_git_check marker to tests requiring real git behavior
description: 'Context: Some tests need to verify actual git repository detection logic
  and should not use the centralized mock.


  Requirements:

  - Run pytest to identify tests that fail with centralized mocking

  - Add @pytest.mark.needs_real_git_check to tests that need real git checks

  - Document why each test needs the marker (in test docstring or comment)

  - Verify marked tests skip the centralized mock via conftest.py logic


  Reference: Task features.bees-tv7

  Files: tests/**/*.py, conftest.py


  Acceptance:

  - All tests that need real git behavior are properly marked

  - Marked tests bypass centralized mock and use real git detection

  - Tests pass with appropriate mocking strategy'
down_dependencies:
- features.bees-o3k
parent: features.bees-tv7
created_at: '2026-02-05T12:46:07.934692'
updated_at: '2026-02-05T12:46:16.502512'
status: open
bees_version: '1.1'
---

Context: Some tests need to verify actual git repository detection logic and should not use the centralized mock.

Requirements:
- Run pytest to identify tests that fail with centralized mocking
- Add @pytest.mark.needs_real_git_check to tests that need real git checks
- Document why each test needs the marker (in test docstring or comment)
- Verify marked tests skip the centralized mock via conftest.py logic

Reference: Task features.bees-tv7
Files: tests/**/*.py, conftest.py

Acceptance:
- All tests that need real git behavior are properly marked
- Marked tests bypass centralized mock and use real git detection
- Tests pass with appropriate mocking strategy
