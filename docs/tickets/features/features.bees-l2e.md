---
id: features.bees-l2e
type: subtask
title: Update README.md with mcp_id_utils module documentation
description: 'Context: Document the new mcp_id_utils module in README.md after extracting
  ID parsing utilities from mcp_server.py.


  Requirements:

  - Add section describing mcp_id_utils module purpose (ID parsing utilities)

  - Document parse_ticket_id() function with parameters and return type

  - Document parse_hive_from_ticket_id() function with parameters and return type

  - Include brief usage examples showing how to parse ticket IDs

  - Explain why these utilities are separate (prevent circular dependencies)


  Files: README.md


  Acceptance Criteria:

  - README.md contains mcp_id_utils section

  - Both functions documented with signatures and examples

  - Documentation explains module purpose and design rationale'
up_dependencies:
- features.bees-jc5
parent: features.bees-pt9
created_at: '2026-02-03T17:03:14.520365'
updated_at: '2026-02-03T18:58:47.539871'
status: completed
bees_version: '1.1'
---

Context: Document the new mcp_id_utils module in README.md after extracting ID parsing utilities from mcp_server.py.

Requirements:
- Add section describing mcp_id_utils module purpose (ID parsing utilities)
- Document parse_ticket_id() function with parameters and return type
- Document parse_hive_from_ticket_id() function with parameters and return type
- Include brief usage examples showing how to parse ticket IDs
- Explain why these utilities are separate (prevent circular dependencies)

Files: README.md

Acceptance Criteria:
- README.md contains mcp_id_utils section
- Both functions documented with signatures and examples
- Documentation explains module purpose and design rationale
