---
id: features.bees-abs
type: subtask
title: Create pytest fixture for repo_root_context
description: |
  Context: Tests need consistent way to set up repo_root context. Create reusable fixture.

  What to Create:
  - Add to tests/conftest.py (or create if doesn't exist)
  - Create fixture `@pytest.fixture def repo_root_ctx(tmp_path):` that:
    1. Creates temporary git repo structure
    2. Uses `with repo_root_context(tmp_path):`
    3. Yields tmp_path for test use
    4. Context automatically cleaned up after test
  - Document fixture usage in docstring

  Files: tests/conftest.py

  Success Criteria:
  - Fixture exists and properly documented
  - Fixture sets up context correctly
  - Context cleanup happens automatically
  - Fixture can be used by all tests
parent: features.bees-aa7
status: completed
created_at: '2026-02-04T19:15:27.000000'
updated_at: '2026-02-04T19:15:27.000000'
bees_version: '1.1'
---

Context: Tests need consistent way to set up repo_root context. Create reusable fixture.

What to Create:
- Add to tests/conftest.py (or create if doesn't exist)
- Create fixture `@pytest.fixture def repo_root_ctx(tmp_path):` that:
  1. Creates temporary git repo structure
  2. Uses `with repo_root_context(tmp_path):`
  3. Yields tmp_path for test use
  4. Context automatically cleaned up after test
- Document fixture usage in docstring

Files: tests/conftest.py

Success Criteria:
- Fixture exists and properly documented
- Fixture sets up context correctly
- Context cleanup happens automatically
- Fixture can be used by all tests
