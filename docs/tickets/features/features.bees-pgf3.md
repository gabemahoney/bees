---
id: features.bees-pgf3
type: subtask
title: Fix multi-hive query tests (test_multi_hive_query.py)
description: |
  Fix 7 skipped tests in test_multi_hive_query.py that need updating for hive-based config system.
  
  These tests are marked with: "Tests need update for hive-based config system"
  
  Affected test class:
  - TestPipelineHiveFiltering (all 7 tests starting at line 171)
  
  Tests cover important multi-hive filtering functionality:
  - Filtering by single hive
  - Filtering by multiple hives
  - Default includes all hives
  - Excludes legacy tickets when filtering
  - Empty hive list handling
  - Hive filter with search stages
  - Hive filter with graph stages
  
  Action: Update test fixtures to use hive-based configuration.
parent: features.bees-pgf
status: completed
priority: 2
up_dependencies: ["features.bees-pgf1"]
created_at: '2026-02-05T05:37:00.000000'
updated_at: '2026-02-05T05:37:00.000000'
bees_version: '1.1'
---

Fix multi-hive query tests for hive-based configuration.
