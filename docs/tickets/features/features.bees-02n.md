---
id: features.bees-02n
type: subtask
title: Identify all modules that import get_repo_root_from_path
description: 'Context: Need to determine which modules depend on `get_repo_root_from_path`
  so we can force their reimport in conftest.py.


  Requirements:

  - Search codebase for all imports of `get_repo_root_from_path`

  - Document the list of module paths that need reload

  - Exclude test files (conftest.py handles test modules separately)


  Files: Search across src/


  Acceptance: Have complete list of production module paths that import `get_repo_root_from_path`


  Reference: Task features.bees-ycr'
down_dependencies:
- features.bees-40m
- features.bees-r9t
- features.bees-47c
parent: features.bees-ycr
created_at: '2026-02-05T12:45:24.308043'
updated_at: '2026-02-05T12:45:40.643828'
status: open
bees_version: '1.1'
---

Context: Need to determine which modules depend on `get_repo_root_from_path` so we can force their reimport in conftest.py.

Requirements:
- Search codebase for all imports of `get_repo_root_from_path`
- Document the list of module paths that need reload
- Exclude test files (conftest.py handles test modules separately)

Files: Search across src/

Acceptance: Have complete list of production module paths that import `get_repo_root_from_path`

Reference: Task features.bees-ycr
