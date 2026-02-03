---
id: features.bees-jgc
type: task
title: Add None check to _sanitize_hive after get_repo_root call
description: "Add check after get_repo_root() call in _sanitize_hive() to raise helpful\
  \ error when None is returned.\n\nAdd after line ~2856:\n```python\nif resolved_repo_root\
  \ is None:\n    raise ValueError(\"Client doesn't support roots protocol. Use repo_root='/path/to/repo'\
  \ parameter.\")\n```\n\nFile: src/mcp_server.py"
labels:
- bug
parent: features.bees-h0a
created_at: '2026-02-03T15:04:52.925750'
updated_at: '2026-02-03T15:16:19.897605'
priority: 1
status: completed
bees_version: '1.1'
---

Add check after get_repo_root() call in _sanitize_hive() to raise helpful error when None is returned.

Add after line ~2856:
```python
if resolved_repo_root is None:
    raise ValueError("Client doesn't support roots protocol. Use repo_root='/path/to/repo' parameter.")
```

File: src/mcp_server.py
