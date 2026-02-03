---
id: features.bees-xcm
type: subtask
title: Extract name normalization documentation
description: 'Extract hive name normalization rules and collision prevention from
  master_plan.md.


  Context: Name normalization is critical for consistent hive identification. Currently
  explained verbosely in multiple places in master_plan.md.


  Requirements:

  - Extract normalization rules (lowercase, spaces→underscores, special chars removed)

  - Explain rationale (consistent IDs, filesystem safety, cross-platform)

  - Document collision detection and prevention

  - Include examples (e.g., "Back End" → "back_end")

  - Keep concise (target ~500 tokens for this section)


  Acceptance Criteria:

  - Rules are clearly stated

  - Rationale is explained

  - Examples demonstrate edge cases

  - Collision handling is documented


  Files: docs/architecture/configuration.md, docs/plans/master_plan.md (source)

  Parent Task: features.bees-654'
up_dependencies:
- features.bees-ixd
down_dependencies:
- features.bees-8it
parent: features.bees-654
created_at: '2026-02-03T16:53:00.628151'
updated_at: '2026-02-03T17:10:45.112547'
status: completed
bees_version: '1.1'
---

Extract hive name normalization rules and collision prevention from master_plan.md.

Context: Name normalization is critical for consistent hive identification. Currently explained verbosely in multiple places in master_plan.md.

Requirements:
- Extract normalization rules (lowercase, spaces→underscores, special chars removed)
- Explain rationale (consistent IDs, filesystem safety, cross-platform)
- Document collision detection and prevention
- Include examples (e.g., "Back End" → "back_end")
- Keep concise (target ~500 tokens for this section)

Acceptance Criteria:
- Rules are clearly stated
- Rationale is explained
- Examples demonstrate edge cases
- Collision handling is documented

Files: docs/architecture/configuration.md, docs/plans/master_plan.md (source)
Parent Task: features.bees-654
