---
id: features.bees-gjg
type: task
title: Centralize mock patching to source module
description: 'Context: Currently mock patches may be applied at import sites, causing
  silent failures when new modules import `get_repo_root_from_path`. This creates
  fragile tests that break unexpectedly.


  What Needs to Change:

  - Update conftest.py to patch `get_repo_root_from_path` only at `src.mcp_repo_utils`
  (source module)

  - Remove any existing patches at import sites throughout test files

  - Verify mock applies to all call sites via source patching


  Why: Patching at the source module ensures the mock applies everywhere the function
  is imported, preventing silent test failures.


  Success Criteria:

  - All patches of `get_repo_root_from_path` are applied at `src.mcp_repo_utils` in
  conftest.py

  - No test files contain direct patches of this function

  - Existing tests continue to pass with centralized mock


  Files: conftest.py, src/mcp_repo_utils.py

  Epic: features.bees-w0c'
down_dependencies:
- features.bees-tv7
parent: features.bees-w0c
children:
- features.bees-lbc
- features.bees-n21
- features.bees-c74
- features.bees-yke
- features.bees-8sk
- features.bees-fqu
- features.bees-0dq
created_at: '2026-02-05T12:44:25.189932'
updated_at: '2026-02-05T14:22:11.556694'
priority: 0
status: completed
bees_version: '1.1'
---

Context: Currently mock patches may be applied at import sites, causing silent failures when new modules import `get_repo_root_from_path`. This creates fragile tests that break unexpectedly.

What Needs to Change:
- Update conftest.py to patch `get_repo_root_from_path` only at `src.mcp_repo_utils` (source module)
- Remove any existing patches at import sites throughout test files
- Verify mock applies to all call sites via source patching

Why: Patching at the source module ensures the mock applies everywhere the function is imported, preventing silent test failures.

Success Criteria:
- All patches of `get_repo_root_from_path` are applied at `src.mcp_repo_utils` in conftest.py
- No test files contain direct patches of this function
- Existing tests continue to pass with centralized mock

Files: conftest.py, src/mcp_repo_utils.py
Epic: features.bees-w0c
