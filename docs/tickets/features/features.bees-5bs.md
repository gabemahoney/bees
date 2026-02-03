---
id: features.bees-5bs
type: task
title: Update get_repo_root error message to mention repo_root parameter
description: 'Error messages about missing repo root are too verbose and tell users
  to "ensure your MCP client supports the roots protocol" when it clearly doesn''t.
  Need to be direct and concise.


  What Needs to Change:

  - Update error message in get_repo_root() (src/mcp_server.py line ~263)

  - Search for all error messages related to repo root determination

  - Update all locations with short, direct message


  New error message (keep it short):

  "Client doesn''t support roots protocol. Use repo_root=''/path/to/repo'' parameter."


  Or similar - acknowledge client lacks roots, tell them to use repo_root param, keep
  it brief.


  File: src/mcp_server.py'
labels:
- bug
parent: features.bees-h0a
created_at: '2026-02-03T13:55:14.356564'
updated_at: '2026-02-03T14:01:47.439609'
priority: 1
status: completed
bees_version: '1.1'
---

Error messages about missing repo root are too verbose and tell users to "ensure your MCP client supports the roots protocol" when it clearly doesn't. Need to be direct and concise.

What Needs to Change:
- Update error message in get_repo_root() (src/mcp_server.py line ~263)
- Search for all error messages related to repo root determination
- Update all locations with short, direct message

New error message (keep it short):
"Client doesn't support roots protocol. Use repo_root='/path/to/repo' parameter."

Or similar - acknowledge client lacks roots, tell them to use repo_root param, keep it brief.

File: src/mcp_server.py
