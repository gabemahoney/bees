---
id: features.bees-mwg
type: subtask
title: Extract corruption detection patterns from master_plan.md
description: "Search master_plan.md for corruption detection and reporting documentation\
  \ and extract the architectural overview for validation.md.\n\nContext: Corruption\
  \ detection identifies database integrity issues through linter validation and generates\
  \ structured reports. Documentation is scattered in master_plan.md.\n\nRequirements:\n\
  - Search master_plan.md for corruption detection sections\n- Extract core architectural\
  \ concepts:\n  - How corruption is detected (linter error categories)\n  - Corruption\
  \ report structure (.bees/corruption_report.json)\n  - Auto-fix vs manual intervention\
  \ decisions\n  - Database integrity guarantees\n- Focus on system design, not implementation\
  \ details\n- Keep extracted content under 500 tokens\n- Reference relevant source\
  \ files\n\nParent Task: features.bees-avl\n\nAcceptance Criteria:\n- Content extracted\
  \ and summarized for validation.md\n- Explains detection patterns and reporting\
  \ strategy\n- References source code locations"
up_dependencies:
- features.bees-h32
down_dependencies:
- features.bees-q7i
parent: features.bees-avl
created_at: '2026-02-03T16:53:41.420313'
updated_at: '2026-02-03T17:38:06.028380'
status: completed
bees_version: '1.1'
---

Search master_plan.md for corruption detection and reporting documentation and extract the architectural overview for validation.md.

Context: Corruption detection identifies database integrity issues through linter validation and generates structured reports. Documentation is scattered in master_plan.md.

Requirements:
- Search master_plan.md for corruption detection sections
- Extract core architectural concepts:
  - How corruption is detected (linter error categories)
  - Corruption report structure (.bees/corruption_report.json)
  - Auto-fix vs manual intervention decisions
  - Database integrity guarantees
- Focus on system design, not implementation details
- Keep extracted content under 500 tokens
- Reference relevant source files

Parent Task: features.bees-avl

Acceptance Criteria:
- Content extracted and summarized for validation.md
- Explains detection patterns and reporting strategy
- References source code locations
