---
id: features.bees-pgc
type: task
title: Fix ticket_factory.py code review issues
description: |
  Fix issues found in code review of features.bees-aa5:
  1. Remove dead code in ticket_factory.py:62,155,251 - unused repo_root variable assignments
  2. Remove unused repo_root parameter from write_ticket_file() in writer.py
  3. Remove unused repo_root parameter from extract_existing_ids_from_all_hives() in id_utils.py
parent: features.bees-nho
up_dependencies: ["features.bees-aa5"]
status: completed
priority: 1
labels: ["bug", "code-review"]
created_at: '2026-02-04T21:30:00.000000'
updated_at: '2026-02-05T13:25:43.000000'
bees_version: '1.1'
---

Fix dead code and unused parameters found in code review.
