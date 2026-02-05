---
id: features.bees-lhm
type: subtask
title: Add TestSerializeFrontmatter to test_writer.py
description: 'Add the TestSerializeFrontmatter class to tests/test_writer.py after
  removing the module-level pytest.skip.


  Context: Moving serialization tests from test_reader.py to their proper location
  in test_writer.py. The class is currently at lines 404-535 in test_reader.py.


  Files to modify:

  - tests/test_writer.py (add TestSerializeFrontmatter class, remove module skip)

  - The class already exists in test_writer.py at lines 102-216, but it''s currently
  skipped due to the module-level skip at line 11


  Implementation:

  1. Remove the module-level pytest.skip (lines 8-11)

  2. The duplicate TestSerializeFrontmatter class (lines 102-216) can stay or be verified
  against the version in test_reader.py (lines 404-535)

  3. Update any legacy ID references (bees-XXX) to use hive-prefixed format (default.bees-XXX)
  if needed


  Acceptance: TestSerializeFrontmatter tests run successfully in test_writer.py'
down_dependencies:
- features.bees-pra
parent: features.bees-9e9
created_at: '2026-02-05T09:50:27.672236'
updated_at: '2026-02-05T09:52:19.172381'
status: completed
bees_version: '1.1'
---

Add the TestSerializeFrontmatter class to tests/test_writer.py after removing the module-level pytest.skip.

Context: Moving serialization tests from test_reader.py to their proper location in test_writer.py. The class is currently at lines 404-535 in test_reader.py.

Files to modify:
- tests/test_writer.py (add TestSerializeFrontmatter class, remove module skip)
- The class already exists in test_writer.py at lines 102-216, but it's currently skipped due to the module-level skip at line 11

Implementation:
1. Remove the module-level pytest.skip (lines 8-11)
2. The duplicate TestSerializeFrontmatter class (lines 102-216) can stay or be verified against the version in test_reader.py (lines 404-535)
3. Update any legacy ID references (bees-XXX) to use hive-prefixed format (default.bees-XXX) if needed

Acceptance: TestSerializeFrontmatter tests run successfully in test_writer.py
