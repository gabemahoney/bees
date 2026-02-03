---
id: features.bees-uen
type: task
title: Update README.md to explain repo_root fallback
description: 'README currently states that bees requires MCP Roots Protocol and lists
  unsupported clients. With the fallback parameter, we now support clients without
  roots if they provide repo_root explicitly.


  What Needs to Change:

  - Update "MCP Client Requirements" section in README.md

  - Change from "requires roots protocol" to "prefers roots protocol with fallback
  support"

  - Add explanation that clients without roots can provide repo_root parameter explicitly

  - Update supported clients list to reflect fallback availability

  - Add example showing how to use tools with explicit repo_root parameter


  Files: README.md


  Epic: features.bees-h0a'
parent: features.bees-h0a
children:
- features.bees-5oa
- features.bees-z4o
- features.bees-rwf
created_at: '2026-02-03T06:41:00.528422'
updated_at: '2026-02-03T06:41:38.656004'
priority: 0
status: open
bees_version: '1.1'
---

README currently states that bees requires MCP Roots Protocol and lists unsupported clients. With the fallback parameter, we now support clients without roots if they provide repo_root explicitly.

What Needs to Change:
- Update "MCP Client Requirements" section in README.md
- Change from "requires roots protocol" to "prefers roots protocol with fallback support"
- Add explanation that clients without roots can provide repo_root parameter explicitly
- Update supported clients list to reflect fallback availability
- Add example showing how to use tools with explicit repo_root parameter

Files: README.md

Epic: features.bees-h0a
