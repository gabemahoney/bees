---
id: features.bees-pgf2
type: subtask
title: Fix query tool tests for hive-based config (test_query_tools.py)
description: |
  Fix ~16 skipped tests in test_query_tools.py that need updating for hive-based config system.
  
  These tests are marked with: "Tests need update for hive-based config system"
  
  Affected test classes:
  - TestExecuteQueryTool (~4 tests starting at line 282)
  - TestExecuteFreeformQuery (~12 tests starting at line 423)
  
  Action: Update test fixtures to use hive-based configuration instead of direct tickets_dir parameter.
  Make tests work with the new PipelineEvaluator that loads from hive config.
parent: features.bees-pgf
status: completed
priority: 2
up_dependencies: ["features.bees-pgf1"]
created_at: '2026-02-05T05:36:00.000000'
updated_at: '2026-02-05T05:36:00.000000'
bees_version: '1.1'
---

Fix query tool tests to work with hive-based configuration.
