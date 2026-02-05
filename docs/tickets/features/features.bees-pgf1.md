---
id: features.bees-pgf1
type: subtask
title: Remove deprecated tickets_dir tests from test_pipeline.py
description: |
  Remove 9 tests in test_pipeline.py that test deprecated tickets_dir parameter functionality.
  
  These tests are marked with: "tickets_dir parameter is deprecated - PipelineEvaluator now loads from hive config"
  
  Tests to remove:
  - test_missing_tickets_dir_raises_error (line 173)
  - test_invalid_yaml_raises_error (line 183)
  - test_skips_tickets_without_id (line 202)
  - test_handles_tickets_without_labels (line 464)
  - test_loads_tickets_from_hive_root_only (line 482)
  - test_filters_by_bees_version_field (line 502)
  - test_excludes_eggs_subdirectory (line 533)
  - test_excludes_evicted_subdirectory (line 572)
  - test_queries_work_with_flat_storage (line 595)
  
  Action: Delete these test methods completely since the functionality they test is deprecated.
parent: features.bees-pgf
status: completed
priority: 2
created_at: '2026-02-05T05:35:00.000000'
updated_at: '2026-02-05T05:35:00.000000'
bees_version: '1.1'
---

Remove deprecated tickets_dir tests - functionality replaced by hive config system.
