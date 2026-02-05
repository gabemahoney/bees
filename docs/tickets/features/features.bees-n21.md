---
id: features.bees-n21
type: subtask
title: Update conftest.py to centralize get_repo_root_from_path mock
description: 'Context: Centralize mock patching at source module (src.mcp_repo_utils)
  to ensure mock applies everywhere the function is imported.


  Requirements:

  - Add/update fixture in conftest.py that patches get_repo_root_from_path at src.mcp_repo_utils.get_repo_root_from_path

  - Use @pytest.fixture with appropriate scope (likely function or module)

  - Mock should return the test tmp_path or similar test directory

  - Ensure fixture is auto-used or easily accessible by all tests


  Files: conftest.py


  Acceptance: conftest.py contains centralized fixture that patches get_repo_root_from_path
  at source module'
parent: features.bees-gjg
created_at: '2026-02-05T12:45:24.530110'
updated_at: '2026-02-05T12:51:19.384292'
status: completed
bees_version: '1.1'
---

Context: Centralize mock patching at source module (src.mcp_repo_utils) to ensure mock applies everywhere the function is imported.

Requirements:
- Add/update fixture in conftest.py that patches get_repo_root_from_path at src.mcp_repo_utils.get_repo_root_from_path
- Use @pytest.fixture with appropriate scope (likely function or module)
- Mock should return the test tmp_path or similar test directory
- Ensure fixture is auto-used or easily accessible by all tests

Files: conftest.py

Acceptance: conftest.py contains centralized fixture that patches get_repo_root_from_path at source module
