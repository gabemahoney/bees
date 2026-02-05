---
id: features.bees-27y
type: task
title: Add pytest marker for real git checks
description: 'Context: Some tests may legitimately need real git repository checks
  rather than mocked behavior. Need a way to mark and configure these tests.


  What Needs to Change:

  - Register `@pytest.mark.needs_real_git_check` marker in pytest configuration (pytest.ini
  or conftest.py)

  - Document marker usage in conftest.py

  - Add marker to any existing tests that require real git checks


  Why: Explicit marker allows tests to opt-out of mocking when real git behavior is
  needed, while keeping default behavior safe.


  Success Criteria:

  - Marker registered in pytest configuration

  - Documentation explains when and how to use the marker

  - Tests marked with `needs_real_git_check` skip the mock patching


  Files: conftest.py, pytest.ini

  Epic: features.bees-w0c'
down_dependencies:
- features.bees-tv7
parent: features.bees-w0c
children:
- features.bees-lhf
- features.bees-7fa
- features.bees-sff
- features.bees-bcf
- features.bees-6i0
- features.bees-b6d
- features.bees-ofx
- features.bees-q2a
created_at: '2026-02-05T12:44:36.171450'
updated_at: '2026-02-05T12:45:59.477490'
priority: 0
status: open
bees_version: '1.1'
---

Context: Some tests may legitimately need real git repository checks rather than mocked behavior. Need a way to mark and configure these tests.

What Needs to Change:
- Register `@pytest.mark.needs_real_git_check` marker in pytest configuration (pytest.ini or conftest.py)
- Document marker usage in conftest.py
- Add marker to any existing tests that require real git checks

Why: Explicit marker allows tests to opt-out of mocking when real git behavior is needed, while keeping default behavior safe.

Success Criteria:
- Marker registered in pytest configuration
- Documentation explains when and how to use the marker
- Tests marked with `needs_real_git_check` skip the mock patching

Files: conftest.py, pytest.ini
Epic: features.bees-w0c
