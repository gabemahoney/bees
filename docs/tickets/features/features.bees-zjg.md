---
id: features.bees-zjg
type: subtask
title: Audit all line number references in testing.md
description: "**Context**: docs/architecture/testing.md contains line references like\
  \ \"tests/conftest.py:190-236\" that become stale as code evolves. Need to identify\
  \ all such references and determine replacement strategy.\n\n**Requirements**:\n\
  - Search testing.md for all patterns matching file paths with line numbers (e.g.,\
  \ `file.py:123`, `file.py:45-67`)\n- Create list of all line number references found\n\
  - For each reference, verify if the line numbers are still accurate\n- Determine\
  \ replacement strategy: use function names/anchors, remove line numbers, or link\
  \ to stable markers\n\n**References**: \n- Parent Task: features.bees-qon\n- File:\
  \ docs/architecture/testing.md\n\n**Acceptance**: Document created listing all line\
  \ references with recommended replacement approach for each."
down_dependencies:
- features.bees-imm
parent: features.bees-qon
created_at: '2026-02-05T09:43:31.744161'
updated_at: '2026-02-05T09:58:30.424181'
status: completed
bees_version: '1.1'
---

**Context**: docs/architecture/testing.md contains line references like "tests/conftest.py:190-236" that become stale as code evolves. Need to identify all such references and determine replacement strategy.

**Requirements**:
- Search testing.md for all patterns matching file paths with line numbers (e.g., `file.py:123`, `file.py:45-67`)
- Create list of all line number references found
- For each reference, verify if the line numbers are still accurate
- Determine replacement strategy: use function names/anchors, remove line numbers, or link to stable markers

**References**: 
- Parent Task: features.bees-qon
- File: docs/architecture/testing.md

**Acceptance**: Document created listing all line references with recommended replacement approach for each.
