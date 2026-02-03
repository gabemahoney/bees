---
id: features.bees-407
type: subtask
title: Run full test suite to verify refactoring
description: 'Execute the complete test suite to ensure removing the dead code checks
  doesn''t break any existing functionality.


  Run:

  ```bash

  poetry run pytest tests/ -v

  ```


  Verify:

  - All existing tests pass

  - No regression in error handling behavior

  - MCP tools still handle missing repo_root correctly by raising exceptions from
  get_repo_root()'
labels:
- testing
up_dependencies:
- features.bees-gxg
- features.bees-f2n
down_dependencies:
- features.bees-csv
parent: features.bees-yp9
created_at: '2026-02-03T12:42:44.317802'
updated_at: '2026-02-03T12:48:46.119698'
status: completed
bees_version: '1.1'
---

Execute the complete test suite to ensure removing the dead code checks doesn't break any existing functionality.

Run:
```bash
poetry run pytest tests/ -v
```

Verify:
- All existing tests pass
- No regression in error handling behavior
- MCP tools still handle missing repo_root correctly by raising exceptions from get_repo_root()
