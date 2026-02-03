---
id: features.bees-vhl
type: task
title: Add None check to _delete_ticket after get_repo_root call
description: "Add check after get_repo_root() call in _delete_ticket() to raise helpful\
  \ error when None is returned.\n\nAdd after line ~1643:\n```python\nif resolved_repo_root\
  \ is None:\n    raise ValueError(\"Client doesn't support roots protocol. Use repo_root='/path/to/repo'\
  \ parameter.\")\n```\n\nFile: src/mcp_server.py"
labels:
- bug
parent: features.bees-h0a
created_at: '2026-02-03T15:04:37.725709'
updated_at: '2026-02-03T15:08:12.629948'
priority: 1
status: completed
bees_version: '1.1'
---

Add check after get_repo_root() call in _delete_ticket() to raise helpful error when None is returned.

Add after line ~1643:
```python
if resolved_repo_root is None:
    raise ValueError("Client doesn't support roots protocol. Use repo_root='/path/to/repo' parameter.")
```

File: src/mcp_server.py
