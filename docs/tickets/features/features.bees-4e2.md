---
id: features.bees-4e2
type: subtask
title: Categorize scan and validation tests
description: 'Context: Target file test_mcp_scan_validate.py should contain ~300 lines
  of scan/validation tests.


  What to Categorize:

  - Tests in TestGetRepoRoot

  - Tests in TestValidateHivePath

  - Tests in TestScanForHiveConfigAutoUpdate

  - Tests in TestScanForHiveSecurity

  - Tests in TestScanForHiveConfigOptimization

  - Tests in TestScanForHiveBugFixes

  - Tests in TestScanForHiveFileVsDirectory

  - Tests in TestScanForHiveExceptionHandling

  - Tests in TestScanForHiveErrorPropagation

  - Tests in TestScanForHiveConfigHandling


  Review each test and determine if it tests scanning for hives or validation logic
  (path validation, repo root detection, etc.)


  Why: These tests belong in the new test_mcp_scan_validate.py file.


  Acceptance Criteria:

  - List shows all scan/validate tests with line numbers

  - Estimate total lines ~300 (verify against target)

  - Each test has clear rationale for categorization


  Reference: Task features.bees-4i1

  Files: tests/test_mcp_server.py'
up_dependencies:
- features.bees-ysm
down_dependencies:
- features.bees-p2j
- features.bees-kgk
parent: features.bees-4i1
created_at: '2026-02-05T16:14:03.419935'
updated_at: '2026-02-05T16:20:39.193077'
status: completed
bees_version: '1.1'
---

Context: Target file test_mcp_scan_validate.py should contain ~300 lines of scan/validation tests.

What to Categorize:
- Tests in TestGetRepoRoot
- Tests in TestValidateHivePath
- Tests in TestScanForHiveConfigAutoUpdate
- Tests in TestScanForHiveSecurity
- Tests in TestScanForHiveConfigOptimization
- Tests in TestScanForHiveBugFixes
- Tests in TestScanForHiveFileVsDirectory
- Tests in TestScanForHiveExceptionHandling
- Tests in TestScanForHiveErrorPropagation
- Tests in TestScanForHiveConfigHandling

Review each test and determine if it tests scanning for hives or validation logic (path validation, repo root detection, etc.)

Why: These tests belong in the new test_mcp_scan_validate.py file.

Acceptance Criteria:
- List shows all scan/validate tests with line numbers
- Estimate total lines ~300 (verify against target)
- Each test has clear rationale for categorization

Reference: Task features.bees-4i1
Files: tests/test_mcp_server.py
