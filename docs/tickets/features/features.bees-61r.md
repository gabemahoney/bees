---
id: features.bees-61r
type: task
title: Update MCP tool docstrings to document repo_root fallback
description: 'Users need to understand when and how to use the repo_root parameter.
  Each of the 11 affected tools needs documentation explaining the fallback mechanism.


  What Needs to Change:

  - Update docstrings for all 11 MCP tool functions in src/mcp_server.py

  - Add explanation of repo_root parameter to Args section

  - Add note explaining: "For MCP clients that don''t support roots protocol, provide
  repo_root explicitly"

  - Update example usage to show both scenarios (with/without repo_root)


  Files: src/mcp_server.py


  Epic: features.bees-h0a'
parent: features.bees-h0a
children:
- features.bees-6sr
- features.bees-f40
- features.bees-cp8
- features.bees-zyt
- features.bees-sg9
- features.bees-3aa
- features.bees-9nv
- features.bees-17q
- features.bees-uj5
- features.bees-b37
created_at: '2026-02-03T06:40:58.399931'
updated_at: '2026-02-03T06:58:47.972929'
priority: 0
status: open
bees_version: '1.1'
---

Users need to understand when and how to use the repo_root parameter. Each of the 11 affected tools needs documentation explaining the fallback mechanism.

What Needs to Change:
- Update docstrings for all 11 MCP tool functions in src/mcp_server.py
- Add explanation of repo_root parameter to Args section
- Add note explaining: "For MCP clients that don't support roots protocol, provide repo_root explicitly"
- Update example usage to show both scenarios (with/without repo_root)

Files: src/mcp_server.py

Epic: features.bees-h0a
