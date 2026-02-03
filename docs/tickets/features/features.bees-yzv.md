---
id: features.bees-yzv
type: subtask
title: Extract configuration file schema documentation
description: 'Extract and refine .bees/config.json schema documentation from master_plan.md.


  Context: Master_plan.md contains verbose explanations of config.json schema mixed
  with implementation details. Need focused architectural overview.


  Requirements:

  - Extract "Configuration Architecture" section from master_plan.md

  - Document .bees/config.json structure

  - Explain hives dictionary schema (key=normalized name, value=HiveConfig)

  - Reference src/config.py instead of duplicating code

  - Keep concise (target ~600 tokens for this section)


  Acceptance Criteria:

  - Schema is clearly documented

  - Examples show structure

  - References config.py for implementation details

  - No code duplication


  Files: docs/architecture/configuration.md, docs/plans/master_plan.md (source)

  Parent Task: features.bees-654'
up_dependencies:
- features.bees-ixd
down_dependencies:
- features.bees-8it
parent: features.bees-654
created_at: '2026-02-03T16:52:54.537889'
updated_at: '2026-02-03T17:10:31.107708'
status: completed
bees_version: '1.1'
---

Extract and refine .bees/config.json schema documentation from master_plan.md.

Context: Master_plan.md contains verbose explanations of config.json schema mixed with implementation details. Need focused architectural overview.

Requirements:
- Extract "Configuration Architecture" section from master_plan.md
- Document .bees/config.json structure
- Explain hives dictionary schema (key=normalized name, value=HiveConfig)
- Reference src/config.py instead of duplicating code
- Keep concise (target ~600 tokens for this section)

Acceptance Criteria:
- Schema is clearly documented
- Examples show structure
- References config.py for implementation details
- No code duplication

Files: docs/architecture/configuration.md, docs/plans/master_plan.md (source)
Parent Task: features.bees-654
