---
id: features.bees-pgf4
type: subtask
title: Resolve sample ticket tests (test_sample_tickets.py)
description: |
  Resolve 13 skipped tests in test_sample_tickets.py that expect sample ticket files to exist.
  
  Tests skip at runtime with: "Sample epic/task/subtask not created yet"
  
  Expected sample files:
  - tickets/epics/sample-epic.md
  - tickets/tasks/sample-task.md
  - tickets/subtasks/sample-subtask.md
  
  Decision needed: Should these sample files exist in the repository?
  
  **Option A**: Create sample ticket files
  - Pros: Useful for onboarding, documentation, testing
  - Cons: More files to maintain
  
  **Option B**: Remove these tests
  - Pros: Less test maintenance
  - Cons: Lose validation that sample tickets work if we add them later
  
  Action: Decide and either create sample files or remove tests.
parent: features.bees-pgf
status: completed
priority: 3
created_at: '2026-02-05T05:38:00.000000'
updated_at: '2026-02-05T05:38:00.000000'
bees_version: '1.1'
---

Decide whether to create sample tickets or remove tests.
