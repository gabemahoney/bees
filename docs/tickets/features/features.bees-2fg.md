---
id: features.bees-2fg
type: subtask
title: Remove TestSerializeFrontmatter from test_reader.py
description: 'Remove the TestSerializeFrontmatter class (lines 404-535) from tests/test_reader.py.


  Context: This class tests the serialize_frontmatter function from src.writer, so
  it logically belongs in test_writer.py alongside other writer tests.


  Files to modify:

  - tests/test_reader.py (remove lines 404-535)

  - Also remove the import of serialize_frontmatter from src.writer (line 12)


  Acceptance: TestSerializeFrontmatter class no longer exists in test_reader.py'
down_dependencies:
- features.bees-1qc
- features.bees-wy8
parent: features.bees-9e9
created_at: '2026-02-05T09:50:21.325837'
updated_at: '2026-02-05T09:52:18.519125'
status: completed
bees_version: '1.1'
---

Remove the TestSerializeFrontmatter class (lines 404-535) from tests/test_reader.py.

Context: This class tests the serialize_frontmatter function from src.writer, so it logically belongs in test_writer.py alongside other writer tests.

Files to modify:
- tests/test_reader.py (remove lines 404-535)
- Also remove the import of serialize_frontmatter from src.writer (line 12)

Acceptance: TestSerializeFrontmatter class no longer exists in test_reader.py
