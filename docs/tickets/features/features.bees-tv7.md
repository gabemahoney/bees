---
id: features.bees-tv7
type: task
title: Update existing tests to work with new mock infrastructure
description: 'Context: After centralizing mock patching and adding module reload logic,
  existing tests may have redundant patches, incorrect assumptions about import order,
  or need the real git check marker.


  What Needs to Change:

  - Scan all test files for patches of `get_repo_root_from_path` and remove redundant
  ones

  - Identify tests that fail with centralized mocking and add `@pytest.mark.needs_real_git_check`
  where appropriate

  - Update tests that rely on specific import order to work with module reloading

  - Run full test suite and fix any breakages caused by infrastructure changes


  Why: Core mocking changes will affect existing tests - need systematic cleanup to
  ensure everything works.


  Success Criteria:

  - Full `pytest` run passes with no failures

  - No redundant patches of `get_repo_root_from_path` remain in test files

  - All tests that need real git behavior are marked appropriately

  - No tests depend on import order


  Files: tests/

  Epic: features.bees-w0c'
up_dependencies:
- features.bees-gjg
- features.bees-ycr
- features.bees-27y
parent: features.bees-w0c
children:
- features.bees-8pf
- features.bees-wsn
- features.bees-90j
- features.bees-o3k
created_at: '2026-02-05T12:44:50.491838'
updated_at: '2026-02-05T16:06:22.316128'
priority: 0
status: completed
bees_version: '1.1'
---

Context: After centralizing mock patching and adding module reload logic, existing tests may have redundant patches, incorrect assumptions about import order, or need the real git check marker.

What Needs to Change:
- Scan all test files for patches of `get_repo_root_from_path` and remove redundant ones
- Identify tests that fail with centralized mocking and add `@pytest.mark.needs_real_git_check` where appropriate
- Update tests that rely on specific import order to work with module reloading
- Run full test suite and fix any breakages caused by infrastructure changes

Why: Core mocking changes will affect existing tests - need systematic cleanup to ensure everything works.

Success Criteria:
- Full `pytest` run passes with no failures
- No redundant patches of `get_repo_root_from_path` remain in test files
- All tests that need real git behavior are marked appropriately
- No tests depend on import order

Files: tests/
Epic: features.bees-w0c
