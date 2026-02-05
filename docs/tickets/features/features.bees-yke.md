---
id: features.bees-yke
type: subtask
title: Update README.md with centralized mocking documentation
description: 'Context: Document the centralized mock patching approach for developers
  working on tests.


  Requirements:

  - Add section to README.md (likely under Testing or Development) explaining centralized
  mock patching

  - Document that get_repo_root_from_path is patched at source module in conftest.py

  - Explain why patching at source module prevents silent test failures

  - Provide example of how to use the fixture in tests if not auto-used


  Files: README.md


  Acceptance: README.md contains clear documentation of centralized mock patching
  approach and usage'
up_dependencies:
- features.bees-lbc
parent: features.bees-gjg
created_at: '2026-02-05T12:45:35.750004'
updated_at: '2026-02-05T12:52:38.336827'
status: completed
bees_version: '1.1'
---

Context: Document the centralized mock patching approach for developers working on tests.

Requirements:
- Add section to README.md (likely under Testing or Development) explaining centralized mock patching
- Document that get_repo_root_from_path is patched at source module in conftest.py
- Explain why patching at source module prevents silent test failures
- Provide example of how to use the fixture in tests if not auto-used

Files: README.md

Acceptance: README.md contains clear documentation of centralized mock patching approach and usage
