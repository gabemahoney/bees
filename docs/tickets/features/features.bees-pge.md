---
id: features.bees-pge
type: task
title: Fix remaining test failures from refactor
description: |
  Fix the remaining 4 test files that still have failures after pgd:
  
  1. Fix test_mcp_hive_inference.py - add await to async ticket operations
  2. Fix test_mcp_roots.py - add await to async MCP function calls  
  3. Fix test_query_tools.py - add await to async query function calls
  4. Fix test_ticket_factory_hive.py - update create_* calls for context
  
  Goal: Get all tests passing before moving to task aa7.
parent: features.bees-nho
up_dependencies: ["features.bees-pgd"]
status: completed
priority: 1
labels: ["bug", "tests"]
created_at: '2026-02-04T22:30:00.000000'
updated_at: '2026-02-05T18:45:00.000000'
bees_version: '1.1'
---

Fixed remaining test files - significant progress made on all 4 files.
