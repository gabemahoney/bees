---
id: features.bees-pgf5
type: subtask
title: Document or fix scan_for_hive limitation (test_mcp_hive_utils.py)
description: |
  Resolve 1 skipped test in test_mcp_hive_utils.py for scan_for_hive auto-update behavior.
  
  Test: test_scan_for_hive_updates_config_on_recovery (line 247)
  Skip reason: "scan_for_hive doesn't auto-update config - known limitation"
  
  Decision needed: Is this a feature we want or an accepted limitation?
  
  **Option A**: Implement auto-update feature
  - Make scan_for_hive() automatically register discovered hives in config
  - Update test to verify this behavior
  - Pros: More automatic, less manual config management
  - Cons: Could surprise users with auto-registration
  
  **Option B**: Accept limitation and improve documentation
  - Keep the skip but add better documentation in code and docs
  - Explain why scan_for_hive() is read-only
  - Pros: Clear separation of concerns (scan vs register)
  - Cons: Users must manually register discovered hives
  
  Action: Decide and either implement feature or improve skip documentation.
parent: features.bees-pgf
status: completed
priority: 3
created_at: '2026-02-05T05:39:00.000000'
updated_at: '2026-02-05T05:39:00.000000'
bees_version: '1.1'
---

Decide on scan_for_hive auto-update behavior.
