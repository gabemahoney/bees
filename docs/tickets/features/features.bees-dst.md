---
id: features.bees-dst
type: subtask
title: Update README.md with bidirectional sync test documentation
description: 'Update README.md to document the new integration test for bidirectional
  relationship syncing.


  Add section describing:

  - Test purpose: Verify MCP functions sync parent/child relationships bidirectionally

  - What it tests: Epic→Task→Subtask children arrays are populated

  - Why it matters: Ensures fixture behavior vs MCP function behavior is documented


  Context: Parent task features.bees-ho6 adds test coverage for bidirectional sync
  behavior noted in test_fixtures.py:174


  Files: README.md


  Acceptance: README.md documents the bidirectional sync integration test'
up_dependencies:
- features.bees-bjf
parent: features.bees-ho6
created_at: '2026-02-05T09:43:42.288945'
updated_at: '2026-02-05T10:01:53.011011'
status: completed
bees_version: '1.1'
---

Update README.md to document the new integration test for bidirectional relationship syncing.

Add section describing:
- Test purpose: Verify MCP functions sync parent/child relationships bidirectionally
- What it tests: Epic→Task→Subtask children arrays are populated
- Why it matters: Ensures fixture behavior vs MCP function behavior is documented

Context: Parent task features.bees-ho6 adds test coverage for bidirectional sync behavior noted in test_fixtures.py:174

Files: README.md

Acceptance: README.md documents the bidirectional sync integration test
