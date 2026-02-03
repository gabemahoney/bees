---
id: features.bees-h1s
type: subtask
title: Update README.md with repo_root parameter documentation
description: '**Context**: After implementing repo_root parameter fallback for all
  MCP tools, need to document this for users whose MCP clients don''t support roots
  protocol.


  **Requirements**:

  - Add section explaining repo_root parameter usage for clients without roots protocol
  support

  - Show example of calling MCP tools with repo_root parameter

  - Explain when repo_root is needed vs optional

  - Document the error message users will see if both roots and repo_root are unavailable


  **Files**: README.md


  **Acceptance**: README clearly documents repo_root parameter and when/how to use
  it'
up_dependencies:
- features.bees-jsp
parent: features.bees-lmo
created_at: '2026-02-03T06:41:39.260430'
updated_at: '2026-02-03T12:32:40.282545'
status: completed
bees_version: '1.1'
---

**Context**: After implementing repo_root parameter fallback for all MCP tools, need to document this for users whose MCP clients don't support roots protocol.

**Requirements**:
- Add section explaining repo_root parameter usage for clients without roots protocol support
- Show example of calling MCP tools with repo_root parameter
- Explain when repo_root is needed vs optional
- Document the error message users will see if both roots and repo_root are unavailable

**Files**: README.md

**Acceptance**: README clearly documents repo_root parameter and when/how to use it
