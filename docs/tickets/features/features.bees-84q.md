---
id: features.bees-84q
type: subtask
title: Update master_plan.md with mcp_index_ops refactoring details
description: 'Context: Document the extraction of index generation to mcp_index_ops
  module.


  What to Update:

  - Document new mcp_index_ops.py module in architecture section

  - Explain why index generation was extracted (modularity, single responsibility)

  - Update mcp_server.py module breakdown to reflect removal of index generation

  - Add to refactoring history/changelog


  Implementation:

  - Find MCP server architecture section

  - Add mcp_index_ops module with responsibilities

  - Update design decisions to include this extraction

  - Document integration points with index_generator module


  Files: docs/plans/master_plan.md


  Acceptance:

  - mcp_index_ops module documented in architecture

  - Extraction rationale explained

  - mcp_server.py description updated

  - Design decisions recorded'
parent: features.bees-zy7
up_dependencies:
- features.bees-mhy
status: open
created_at: '2026-02-03T17:03:28.173188'
updated_at: '2026-02-03T17:03:28.173190'
bees_version: '1.1'
---

Context: Document the extraction of index generation to mcp_index_ops module.

What to Update:
- Document new mcp_index_ops.py module in architecture section
- Explain why index generation was extracted (modularity, single responsibility)
- Update mcp_server.py module breakdown to reflect removal of index generation
- Add to refactoring history/changelog

Implementation:
- Find MCP server architecture section
- Add mcp_index_ops module with responsibilities
- Update design decisions to include this extraction
- Document integration points with index_generator module

Files: docs/plans/master_plan.md

Acceptance:
- mcp_index_ops module documented in architecture
- Extraction rationale explained
- mcp_server.py description updated
- Design decisions recorded
