---
id: features.bees-sff
type: subtask
title: Update mock_git_check fixture to skip patching for marked tests
description: 'Context: Tests with needs_real_git_check marker should bypass git mocking.


  Requirements:

  - Modify mock_git_check fixture in conftest.py

  - Check if test has needs_real_git_check marker

  - Skip patching if marker present, otherwise apply mock as usual

  - Use pytest request.node.get_closest_marker(''needs_real_git_check'') pattern


  Files: conftest.py


  Acceptance: Tests with marker run against real git checks, tests without marker
  use mocked behavior'
parent: features.bees-27y
status: open
created_at: '2026-02-05T12:45:38.002668'
updated_at: '2026-02-05T12:45:38.002674'
bees_version: '1.1'
---

Context: Tests with needs_real_git_check marker should bypass git mocking.

Requirements:
- Modify mock_git_check fixture in conftest.py
- Check if test has needs_real_git_check marker
- Skip patching if marker present, otherwise apply mock as usual
- Use pytest request.node.get_closest_marker('needs_real_git_check') pattern

Files: conftest.py

Acceptance: Tests with marker run against real git checks, tests without marker use mocked behavior
