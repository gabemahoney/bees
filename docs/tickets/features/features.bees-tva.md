---
id: features.bees-tva
type: subtask
title: Update _add_named_query docstring to document implicit path resolution
description: 'Add a note to the _add_named_query docstring explaining that it uses
  implicit path resolution via get_client_repo_root() internally, which is why it
  doesn''t require a repo_root parameter like other MCP tools.


  Context: This function differs from most other MCP tools by not accepting ctx/repo_root
  parameters. This is intentional but should be documented to avoid confusion.


  File: /Users/gmahoney/projects/bees/src/mcp_server.py (line ~1777)


  Add a note in the docstring after the main description explaining:

  - Uses implicit path resolution via get_client_repo_root()

  - This is why no ctx or repo_root parameter is needed

  - Falls back to environment-based detection for clients without roots protocol support


  Acceptance: Docstring clearly explains the implicit path resolution design choice'
parent: features.bees-cyh
created_at: '2026-02-03T12:36:08.153353'
updated_at: '2026-02-03T12:46:15.503586'
status: completed
bees_version: '1.1'
---

Add a note to the _add_named_query docstring explaining that it uses implicit path resolution via get_client_repo_root() internally, which is why it doesn't require a repo_root parameter like other MCP tools.

Context: This function differs from most other MCP tools by not accepting ctx/repo_root parameters. This is intentional but should be documented to avoid confusion.

File: /Users/gmahoney/projects/bees/src/mcp_server.py (line ~1777)

Add a note in the docstring after the main description explaining:
- Uses implicit path resolution via get_client_repo_root()
- This is why no ctx or repo_root parameter is needed
- Falls back to environment-based detection for clients without roots protocol support

Acceptance: Docstring clearly explains the implicit path resolution design choice
