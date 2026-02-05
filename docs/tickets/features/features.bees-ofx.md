---
id: features.bees-ofx
type: subtask
title: Add unit tests for needs_real_git_check marker behavior
description: 'Context: Need to verify marker correctly skips mocking.


  Requirements:

  - Add test verifying marker registration

  - Add test showing marked test bypasses mock_git_check patching

  - Add test showing unmarked test still gets mocked behavior

  - Test edge cases (marker inheritance, fixture interaction)


  Files: tests/test_conftest.py or new test file


  Acceptance: Tests verify marker behavior and fixture conditional logic'
up_dependencies:
- features.bees-lhf
down_dependencies:
- features.bees-q2a
parent: features.bees-27y
created_at: '2026-02-05T12:45:52.913201'
updated_at: '2026-02-05T12:45:59.479869'
status: open
bees_version: '1.1'
---

Context: Need to verify marker correctly skips mocking.

Requirements:
- Add test verifying marker registration
- Add test showing marked test bypasses mock_git_check patching
- Add test showing unmarked test still gets mocked behavior
- Test edge cases (marker inheritance, fixture interaction)

Files: tests/test_conftest.py or new test file

Acceptance: Tests verify marker behavior and fixture conditional logic
