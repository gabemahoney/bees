---
id: features.bees-99t
type: subtask
title: Categorize tests into lifecycle, scan_validate, and remaining groups
description: "Context: Identify which tests belong in each target file based on what\
  \ they test.\n\nRequirements:\n- Review each test function to understand what it\
  \ tests\n- Categorize as:\n  - lifecycle: server startup, shutdown, tool registration,\
  \ initialization\n  - scan_validate: file scanning, hive discovery, validation logic\n\
  \  - remaining: all other tool tests (ticket operations, queries, etc.)\n- Verify\
  \ categories align with expected line counts (~400 lifecycle, ~300 scan_validate,\
  \ ~1,600 remaining)\n\nAcceptance Criteria:\n- Each test assigned to one category\n\
  - Category assignments are logical based on test content\n- Line count distribution\
  \ roughly matches Epic estimates\n\nReference: Parent Task features.bees-4i1, Epic\
  \ features.bees-5y8"
up_dependencies:
- features.bees-a9n
down_dependencies:
- features.bees-58n
parent: features.bees-4i1
created_at: '2026-02-05T16:15:35.844466'
updated_at: '2026-02-05T16:21:47.587908'
status: completed
bees_version: '1.1'
---

Context: Identify which tests belong in each target file based on what they test.

Requirements:
- Review each test function to understand what it tests
- Categorize as:
  - lifecycle: server startup, shutdown, tool registration, initialization
  - scan_validate: file scanning, hive discovery, validation logic
  - remaining: all other tool tests (ticket operations, queries, etc.)
- Verify categories align with expected line counts (~400 lifecycle, ~300 scan_validate, ~1,600 remaining)

Acceptance Criteria:
- Each test assigned to one category
- Category assignments are logical based on test content
- Line count distribution roughly matches Epic estimates

Reference: Parent Task features.bees-4i1, Epic features.bees-5y8
