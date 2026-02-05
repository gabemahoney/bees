---
id: features.bees-bcf
type: subtask
title: Identify and mark existing tests requiring real git checks
description: 'Context: Some existing tests may need real git behavior instead of mocks.


  Requirements:

  - Search test files for tests that may need real git checks

  - Add @pytest.mark.needs_real_git_check decorator to identified tests

  - Document reason in test docstring or comment


  Files: tests/ directory (test_*.py files)


  Acceptance: Tests requiring real git behavior are properly decorated with marker'
parent: features.bees-27y
created_at: '2026-02-05T12:45:40.902742'
updated_at: '2026-02-05T15:47:45.206662'
status: completed
bees_version: '1.1'
---

Context: Some existing tests may need real git behavior instead of mocks.

Requirements:
- Search test files for tests that may need real git checks
- Add @pytest.mark.needs_real_git_check decorator to identified tests
- Document reason in test docstring or comment

Files: tests/ directory (test_*.py files)

Acceptance: Tests requiring real git behavior are properly decorated with marker
