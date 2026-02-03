---
id: features.bees-8u7
type: subtask
title: Update test_get_client_repo_root_raises_on_empty_roots to expect None return
description: '**Context:**

  The test at tests/test_mcp_roots.py:37 expects get_client_repo_root() to raise ValueError
  when list_roots() returns an empty list. However, commit 715e452 intentionally changed
  this behavior to return None instead (for graceful degradation when clients don''t
  support roots protocol).


  **Task:**

  Update the test `test_get_client_repo_root_raises_on_empty_roots` in tests/test_mcp_roots.py
  (lines 27-38) to:

  1. Rename test to `test_get_client_repo_root_returns_none_on_empty_roots`

  2. Remove the `pytest.raises(ValueError)` assertion

  3. Change to expect `result = await get_client_repo_root(ctx); assert result is
  None`

  4. Update docstring to reflect new behavior: "Test returns None when client provides
  empty roots"


  **Acceptance:**

  - Test renamed and updated to expect None return value

  - Test passes with current implementation

  - Docstring accurately describes behavior'
down_dependencies:
- features.bees-aqv
- features.bees-s3s
- features.bees-k40
parent: features.bees-o0l
created_at: '2026-02-03T12:36:03.093524'
updated_at: '2026-02-03T12:37:06.044984'
status: completed
bees_version: '1.1'
---

**Context:**
The test at tests/test_mcp_roots.py:37 expects get_client_repo_root() to raise ValueError when list_roots() returns an empty list. However, commit 715e452 intentionally changed this behavior to return None instead (for graceful degradation when clients don't support roots protocol).

**Task:**
Update the test `test_get_client_repo_root_raises_on_empty_roots` in tests/test_mcp_roots.py (lines 27-38) to:
1. Rename test to `test_get_client_repo_root_returns_none_on_empty_roots`
2. Remove the `pytest.raises(ValueError)` assertion
3. Change to expect `result = await get_client_repo_root(ctx); assert result is None`
4. Update docstring to reflect new behavior: "Test returns None when client provides empty roots"

**Acceptance:**
- Test renamed and updated to expect None return value
- Test passes with current implementation
- Docstring accurately describes behavior
