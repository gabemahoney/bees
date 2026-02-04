---
id: features.bees-1m0
type: epic
title: 'NAME_SIMPLE: Simplified Hive Rename Operation'
description: |
  Simplify _rename_hive() to only update .bees/config.json and .hive/identity.json. Remove file renaming, frontmatter ID updates, and cross-reference scanning (not needed since filenames dont contain hive).
  
  Acceptance Criteria:
  - User renames hive from "features" to "new_features"
  - Ticket files remain unchanged (myproject.a1B2.md stays same)
  - Config and .hive/identity.json are updated correctly
  - All tickets still accessible via MCP after rename
  - Agent creates integration tests verifying hive rename simplicity
  
  Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/-1_simplified_naming/PRD.md
status: open
labels:
- not-started
up_dependencies:
- features.bees-5sc
down_dependencies:
- features.bees-en9
created_at: '2026-02-04T00:47:49.168719'
updated_at: '2026-02-04T00:47:49.168719'
bees_version: '1.1'
---

Simplify _rename_hive() to only update .bees/config.json and .hive/identity.json. Remove file renaming, frontmatter ID updates, and cross-reference scanning (not needed since filenames dont contain hive).

Acceptance Criteria:
- User renames hive from "features" to "new_features"
- Ticket files remain unchanged (myproject.a1B2.md stays same)
- Config and .hive/identity.json are updated correctly
- All tickets still accessible via MCP after rename
- Agent creates integration tests verifying hive rename simplicity

Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/-1_simplified_naming/PRD.md
