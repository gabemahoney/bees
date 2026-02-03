---
id: features.bees-5oa
type: subtask
title: Update MCP Client Requirements section to reflect fallback support
description: '**Context**: README currently states bees requires MCP Roots Protocol.
  With the new fallback parameter, clients without roots can still use bees by providing
  repo_root explicitly.


  **Requirements**:

  - Locate "MCP Client Requirements" section in README.md

  - Change language from "requires roots protocol" to "prefers roots protocol with
  fallback support"

  - Explain that clients without roots can provide repo_root parameter explicitly

  - Make it clear that roots is preferred but not mandatory


  **Files**: README.md


  **Acceptance**: Section accurately describes both roots-based and fallback approaches
  without implying roots is mandatory.'
parent: features.bees-uen
status: open
created_at: '2026-02-03T06:41:26.942827'
updated_at: '2026-02-03T06:41:26.942828'
bees_version: '1.1'
---

**Context**: README currently states bees requires MCP Roots Protocol. With the new fallback parameter, clients without roots can still use bees by providing repo_root explicitly.

**Requirements**:
- Locate "MCP Client Requirements" section in README.md
- Change language from "requires roots protocol" to "prefers roots protocol with fallback support"
- Explain that clients without roots can provide repo_root parameter explicitly
- Make it clear that roots is preferred but not mandatory

**Files**: README.md

**Acceptance**: Section accurately describes both roots-based and fallback approaches without implying roots is mandatory.
