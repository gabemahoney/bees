---
id: features.bees-3cx
type: task
title: Add None check to _list_hives after get_repo_root call
description: "Add check after get_repo_root() call in _list_hives() to raise helpful\
  \ error when None is returned. USER REPORTED THIS ONE.\n\nAdd after line ~2294:\n\
  ```python\nif resolved_repo_root is None:\n    raise ValueError(\"Client doesn't\
  \ support roots protocol. Use repo_root='/path/to/repo' parameter.\")\n```\n\nFile:\
  \ src/mcp_server.py"
labels:
- bug
parent: features.bees-h0a
created_at: '2026-02-03T15:04:47.253142'
updated_at: '2026-02-03T15:12:38.717399'
priority: 1
status: completed
bees_version: '1.1'
---

Add check after get_repo_root() call in _list_hives() to raise helpful error when None is returned. USER REPORTED THIS ONE.

Add after line ~2294:
```python
if resolved_repo_root is None:
    raise ValueError("Client doesn't support roots protocol. Use repo_root='/path/to/repo' parameter.")
```

File: src/mcp_server.py
