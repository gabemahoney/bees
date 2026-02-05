---
id: features.bees-c74
type: subtask
title: Remove import-site patches from all test files
description: 'Context: Remove redundant patches now that centralized source-module
  patching is in place.


  Requirements:

  - Remove all @patch decorators and patch.object calls for get_repo_root_from_path
  from test files

  - Remove any manual mock setup for this function in test bodies

  - Update test function signatures to remove patch parameters no longer needed

  - Ensure tests use the centralized fixture from conftest.py instead


  Files: All test files identified in audit subtask


  Acceptance: No test files contain direct patches of get_repo_root_from_path; all
  rely on conftest.py fixture'
down_dependencies:
- features.bees-0dq
parent: features.bees-gjg
created_at: '2026-02-05T12:45:28.355627'
updated_at: '2026-02-05T12:52:19.948825'
status: completed
bees_version: '1.1'
---

Context: Remove redundant patches now that centralized source-module patching is in place.

Requirements:
- Remove all @patch decorators and patch.object calls for get_repo_root_from_path from test files
- Remove any manual mock setup for this function in test bodies
- Update test function signatures to remove patch parameters no longer needed
- Ensure tests use the centralized fixture from conftest.py instead

Files: All test files identified in audit subtask

Acceptance: No test files contain direct patches of get_repo_root_from_path; all rely on conftest.py fixture
