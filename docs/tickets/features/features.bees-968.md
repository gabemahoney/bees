---
id: features.bees-968
type: subtask
title: Remove Architecture section from README.md
description: '**Context**: README.md contains an "Architecture" section (lines 118-147)
  with implementation details (Python imports, internal module docs) that violates
  README best practices - "No implementation details in Readme".


  **What to do**:

  - Remove lines 118-147 from /Users/gmahoney/projects/bees/README.md

  - Delete the entire "## Architecture" section including the mcp_id_utils module
  documentation

  - Ensure section break between "Ticket ID Format" (ends line 116) and "MCP Commands"
  (starts line 149) remains clean


  **Files**: /Users/gmahoney/projects/bees/README.md


  **Acceptance**: Architecture section completely removed, README flows cleanly from
  "Ticket ID Format" to "MCP Commands"'
down_dependencies:
- features.bees-wvt
parent: features.bees-w4v
created_at: '2026-02-03T19:07:42.867273'
updated_at: '2026-02-03T19:12:39.793795'
status: completed
bees_version: '1.1'
---

**Context**: README.md contains an "Architecture" section (lines 118-147) with implementation details (Python imports, internal module docs) that violates README best practices - "No implementation details in Readme".

**What to do**:
- Remove lines 118-147 from /Users/gmahoney/projects/bees/README.md
- Delete the entire "## Architecture" section including the mcp_id_utils module documentation
- Ensure section break between "Ticket ID Format" (ends line 116) and "MCP Commands" (starts line 149) remains clean

**Files**: /Users/gmahoney/projects/bees/README.md

**Acceptance**: Architecture section completely removed, README flows cleanly from "Ticket ID Format" to "MCP Commands"
