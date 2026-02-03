---
id: features.bees-pac
type: task
title: Add None check to _show_ticket after get_repo_root call
description: "Add check after get_repo_root() call in _show_ticket() to raise helpful\
  \ error when None is returned.\n\nAdd after line ~2026:\n```python\nif resolved_repo_root\
  \ is None:\n    raise ValueError(\"Client doesn't support roots protocol. Use repo_root='/path/to/repo'\
  \ parameter.\")\n```\n\nFile: src/mcp_server.py"
labels:
- bug
parent: features.bees-h0a
created_at: '2026-02-03T15:04:43.681166'
updated_at: '2026-02-03T15:10:23.805116'
priority: 1
status: completed
bees_version: '1.1'
---

Add check after get_repo_root() call in _show_ticket() to raise helpful error when None is returned.

Add after line ~2026:
```python
if resolved_repo_root is None:
    raise ValueError("Client doesn't support roots protocol. Use repo_root='/path/to/repo' parameter.")
```

File: src/mcp_server.py
