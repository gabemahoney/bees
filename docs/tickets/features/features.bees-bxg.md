---
id: features.bees-bxg
type: epic
title: 'NAME_SIMPLE: Configuration Schema - Add Repository Name'
description: |
  Add repo_name field to client .bees/config.json. Update MCP server to read and validate this field. Remove allow_cross_hive_dependencies field (always false now). Schema stays at version 1.0.
  
  Acceptance Criteria:
  - User can add "repo_name": "myproject" to their .bees/config.json
  - MCP server validates repo_name is present and is a valid identifier
  - MCP server initialization prompts user for repo_name during setup
  - Agent creates unit tests verifying config validation
  
  Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/-1_simplified_naming/PRD.md
status: open
labels:
- not-started
down_dependencies:
- features.bees-18h
created_at: '2026-02-04T00:47:49.168719'
updated_at: '2026-02-04T00:47:49.168719'
bees_version: '1.1'
---

Add repo_name field to client .bees/config.json. Update MCP server to read and validate this field. Remove allow_cross_hive_dependencies field (always false now). Schema stays at version 1.0.

Acceptance Criteria:
- User can add "repo_name": "myproject" to their .bees/config.json
- MCP server validates repo_name is present and is a valid identifier
- MCP server initialization prompts user for repo_name during setup
- Agent creates unit tests verifying config validation

Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/-1_simplified_naming/PRD.md
