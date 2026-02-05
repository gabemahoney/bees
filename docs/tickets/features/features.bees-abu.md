---
id: features.bees-abu
type: subtask
title: Add concurrent context test
description: |
  Context: Verify that concurrent async tasks with different repo_roots don't interfere with each other.

  What to Test:
  - Create test function test_concurrent_repo_contexts
  - Set up 3+ different temporary repo paths
  - Create async tasks that each:
    1. Set repo_root_context with their specific path
    2. Call get_repo_root() multiple times
    3. Verify they always get their own path back
    4. Sleep randomly to increase interleaving
  - Run tasks concurrently with asyncio.gather()
  - Verify all tasks complete successfully with correct isolated contexts

  Files: tests/test_repo_context.py (add to existing file)

  Success Criteria:
  - Test creates multiple concurrent contexts
  - Test verifies context isolation
  - Test passes consistently (run multiple times)
  - No context leakage between concurrent tasks
parent: features.bees-aa7
status: completed
created_at: '2026-02-04T19:15:29.000000'
updated_at: '2026-02-04T19:15:29.000000'
bees_version: '1.1'
---

Context: Verify that concurrent async tasks with different repo_roots don't interfere with each other.

What to Test:
- Create test function test_concurrent_repo_contexts
- Set up 3+ different temporary repo paths
- Create async tasks that each:
  1. Set repo_root_context with their specific path
  2. Call get_repo_root() multiple times
  3. Verify they always get their own path back
  4. Sleep randomly to increase interleaving
- Run tasks concurrently with asyncio.gather()
- Verify all tasks complete successfully with correct isolated contexts

Files: tests/test_repo_context.py (add to existing file)

Success Criteria:
- Test creates multiple concurrent contexts
- Test verifies context isolation
- Test passes consistently (run multiple times)
- No context leakage between concurrent tasks
