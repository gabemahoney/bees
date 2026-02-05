---
id: features.bees-wy8
type: subtask
title: Update master_plan.md with test refactoring details
description: 'Document the test suite reorganization in master_plan.md.


  Context: Part of the "Remove Legacy Skipped Tests" epic (features.bees-5va). TestSerializeFrontmatter
  class has been moved from test_reader.py to test_writer.py.


  Requirements:

  - Document that serialization tests now live in test_writer.py

  - Note that test_reader.py now only contains reader/parser/validator tests

  - Record this as part of the test cleanup effort


  Files to modify:

  - docs/master_plan.md


  Acceptance: master_plan.md documents the test reorganization and improved test organization'
up_dependencies:
- features.bees-2fg
parent: features.bees-9e9
created_at: '2026-02-05T09:50:41.016596'
updated_at: '2026-02-05T09:52:47.412751'
status: completed
bees_version: '1.1'
---

Document the test suite reorganization in master_plan.md.

Context: Part of the "Remove Legacy Skipped Tests" epic (features.bees-5va). TestSerializeFrontmatter class has been moved from test_reader.py to test_writer.py.

Requirements:
- Document that serialization tests now live in test_writer.py
- Note that test_reader.py now only contains reader/parser/validator tests
- Record this as part of the test cleanup effort

Files to modify:
- docs/master_plan.md

Acceptance: master_plan.md documents the test reorganization and improved test organization
