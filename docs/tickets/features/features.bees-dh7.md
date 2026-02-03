---
id: features.bees-dh7
type: task
title: Add None check to _abandon_hive after get_repo_root call
description: "Add check after get_repo_root() call in _abandon_hive() to raise helpful\
  \ error when None is returned.\n\nAdd after line ~2373:\n```python\nif resolved_repo_root\
  \ is None:\n    raise ValueError(\"Client doesn't support roots protocol. Use repo_root='/path/to/repo'\
  \ parameter.\")\n```\n\nFile: src/mcp_server.py"
labels:
- bug
parent: features.bees-h0a
created_at: '2026-02-03T15:04:49.158516'
updated_at: '2026-02-03T15:14:09.933931'
priority: 1
status: completed
bees_version: '1.1'
---

Add check after get_repo_root() call in _abandon_hive() to raise helpful error when None is returned.

Add after line ~2373:
```python
if resolved_repo_root is None:
    raise ValueError("Client doesn't support roots protocol. Use repo_root='/path/to/repo' parameter.")
```

File: src/mcp_server.py
