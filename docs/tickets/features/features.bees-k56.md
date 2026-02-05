---
id: features.bees-k56
type: task
title: Document mock patching approach
description: 'Context: The mock patching pattern needs clear documentation so future
  developers understand why it''s structured this way and how to maintain it.


  What Needs to Change:

  - Add comprehensive docstring to conftest.py explaining the patching strategy

  - Document why source-level patching is used

  - Provide examples of correct and incorrect patching

  - Explain module reload mechanism


  Why: Clear documentation prevents future regressions and helps maintainers understand
  the testing infrastructure.


  Success Criteria:

  - conftest.py contains detailed comments explaining mock patching approach

  - Documentation includes examples of correct usage

  - Explains relationship between patching, reloading, and the needs_real_git_check
  marker


  Files: conftest.py

  Epic: features.bees-w0c'
parent: features.bees-w0c
children:
- features.bees-j2g
- features.bees-uoj
created_at: '2026-02-05T12:44:40.084026'
updated_at: '2026-02-05T15:58:00.287183'
priority: 0
status: completed
bees_version: '1.1'
---

Context: The mock patching pattern needs clear documentation so future developers understand why it's structured this way and how to maintain it.

What Needs to Change:
- Add comprehensive docstring to conftest.py explaining the patching strategy
- Document why source-level patching is used
- Provide examples of correct and incorrect patching
- Explain module reload mechanism

Why: Clear documentation prevents future regressions and helps maintainers understand the testing infrastructure.

Success Criteria:
- conftest.py contains detailed comments explaining mock patching approach
- Documentation includes examples of correct usage
- Explains relationship between patching, reloading, and the needs_real_git_check marker

Files: conftest.py
Epic: features.bees-w0c
