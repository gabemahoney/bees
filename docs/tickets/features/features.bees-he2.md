---
id: features.bees-he2
type: task
title: Add None check to _create_ticket after get_repo_root call
description: "Add check after get_repo_root() call in _create_ticket() to raise helpful\
  \ error when None is returned (roots protocol unavailable and no repo_root provided).\n\
  \nAdd after line ~1166:\n```python\nif resolved_repo_root is None:\n    raise ValueError(\"\
  Client doesn't support roots protocol. Use repo_root='/path/to/repo' parameter.\"\
  )\n```\n\nFile: src/mcp_server.py"
labels:
- bug
parent: features.bees-h0a
created_at: '2026-02-03T15:04:33.970873'
updated_at: '2026-02-03T15:06:46.154550'
priority: 1
status: completed
bees_version: '1.1'
---

Add check after get_repo_root() call in _create_ticket() to raise helpful error when None is returned (roots protocol unavailable and no repo_root provided).

Add after line ~1166:
```python
if resolved_repo_root is None:
    raise ValueError("Client doesn't support roots protocol. Use repo_root='/path/to/repo' parameter.")
```

File: src/mcp_server.py
