---
id: features.bees-4a7
type: subtask
title: Update master_plan.md to reference validation.md
description: 'Update master_plan.md to remove or condense the extracted validation
  content and add a reference to the new docs/architecture/validation.md.


  Context: Part of the master_plan.md refactoring to reduce from 38k+ tokens to more
  focused documentation. Extracted sections should be replaced with brief references.


  Requirements:

  - Locate "Linter Infrastructure Architecture" section (around line 1970)

  - Replace verbose content with brief summary and reference: "See docs/architecture/validation.md
  for detailed linter architecture"

  - Replace or condense index generation content with reference to validation.md

  - Replace or condense corruption detection content with reference to validation.md

  - Ensure cross-references are clear

  - Maintain master_plan.md readability


  Parent Task: features.bees-avl

  Source File: docs/plans/master_plan.md

  Target File: docs/architecture/validation.md


  Acceptance Criteria:

  - master_plan.md updated with references to validation.md

  - Verbose validation content removed or condensed

  - Document flow maintained

  - Token count reduced'
parent: features.bees-avl
up_dependencies:
- features.bees-q7i
status: open
created_at: '2026-02-03T16:53:56.391026'
updated_at: '2026-02-03T16:53:56.391030'
bees_version: '1.1'
---

Update master_plan.md to remove or condense the extracted validation content and add a reference to the new docs/architecture/validation.md.

Context: Part of the master_plan.md refactoring to reduce from 38k+ tokens to more focused documentation. Extracted sections should be replaced with brief references.

Requirements:
- Locate "Linter Infrastructure Architecture" section (around line 1970)
- Replace verbose content with brief summary and reference: "See docs/architecture/validation.md for detailed linter architecture"
- Replace or condense index generation content with reference to validation.md
- Replace or condense corruption detection content with reference to validation.md
- Ensure cross-references are clear
- Maintain master_plan.md readability

Parent Task: features.bees-avl
Source File: docs/plans/master_plan.md
Target File: docs/architecture/validation.md

Acceptance Criteria:
- master_plan.md updated with references to validation.md
- Verbose validation content removed or condensed
- Document flow maintained
- Token count reduced
