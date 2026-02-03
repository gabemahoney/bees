---
id: features.bees-o4d
type: subtask
title: Update README.md with get_repo_root error handling documentation
description: "**Context**: After fixing docstring/implementation mismatch in get_repo_root\
  \ function, ensure README.md documents the error handling behavior for users.\n\n\
  **Requirements**: \n- Document in README.md how get_repo_root handles cases where\
  \ roots protocol is unavailable\n- Explain what error/return value users should\
  \ expect\n- Include examples if helpful\n\n**Files Affected**:\n- README.md\n\n\
  **Parent Task**: features.bees-lw7\n**Parent Epic**: features.bees-h0a (Need to\
  \ support MCP clients that dont use roots)\n\n**Acceptance**: README.md clearly\
  \ explains get_repo_root error handling behavior for users."
up_dependencies:
- features.bees-rur
parent: features.bees-lw7
created_at: '2026-02-03T12:42:54.572433'
updated_at: '2026-02-03T12:52:34.612785'
status: completed
bees_version: '1.1'
---

**Context**: After fixing docstring/implementation mismatch in get_repo_root function, ensure README.md documents the error handling behavior for users.

**Requirements**: 
- Document in README.md how get_repo_root handles cases where roots protocol is unavailable
- Explain what error/return value users should expect
- Include examples if helpful

**Files Affected**:
- README.md

**Parent Task**: features.bees-lw7
**Parent Epic**: features.bees-h0a (Need to support MCP clients that dont use roots)

**Acceptance**: README.md clearly explains get_repo_root error handling behavior for users.
