---
id: features.bees-pga
type: task
title: Fix MCP entry point calls to config.py functions
description: |
  Remove repo_root parameters from MCP entry point calls to config.py functions, since config.py was refactored in aa3 to read from context.
  
  Fix calls in:
  - mcp_hive_ops.py: lines 135, 249, 432, 517, 534, 615, 647, 992
  - mcp_ticket_ops.py: lines 134, 162, 409, 644, 778
  
  All these calls should remove the repo_root/resolved_root parameter and rely on context.
parent: features.bees-nho
up_dependencies: ["features.bees-aa3"]
status: completed
priority: 1
labels: ["bug", "code-review"]
created_at: '2026-02-04T20:30:00.000000'
updated_at: '2026-02-04T21:45:00.000000'
bees_version: '1.1'
---

Remove repo_root parameters from MCP entry point calls to config.py functions.
