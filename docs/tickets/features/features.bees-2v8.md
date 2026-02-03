---
id: features.bees-2v8
type: task
title: Remove repo_root fallback documentation from README
description: 'The repo_root parameter is intended for LLM agents using MCP clients
  without roots protocol support. Since LLMs read function docstrings automatically
  and human users never directly call MCP tools, this documentation clutters the README
  unnecessarily.


  What Needs to Change:

  - Remove the "Fallback for Clients Without Roots Support" section from README.md
  (lines 22-51)

  - Remove the warning about basic MCP clients from the MCP Client Requirements section
  (line 20)

  - Keep only the supported clients list (Claude Desktop, OpenCode)


  The docstrings in src/mcp_server.py should remain as they are read by LLM agents.


  File: README.md'
labels:
- documentation
parent: features.bees-h0a
created_at: '2026-02-03T13:53:34.354563'
updated_at: '2026-02-03T13:57:46.822906'
priority: 1
status: completed
bees_version: '1.1'
---

The repo_root parameter is intended for LLM agents using MCP clients without roots protocol support. Since LLMs read function docstrings automatically and human users never directly call MCP tools, this documentation clutters the README unnecessarily.

What Needs to Change:
- Remove the "Fallback for Clients Without Roots Support" section from README.md (lines 22-51)
- Remove the warning about basic MCP clients from the MCP Client Requirements section (line 20)
- Keep only the supported clients list (Claude Desktop, OpenCode)

The docstrings in src/mcp_server.py should remain as they are read by LLM agents.

File: README.md
