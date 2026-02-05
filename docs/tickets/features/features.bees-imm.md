---
id: features.bees-imm
type: subtask
title: Replace line number references with stable identifiers
description: "**Context**: Remove stale line number references from docs/architecture/testing.md\
  \ and replace with stable alternatives like function/class names or descriptive\
  \ text that won't become outdated.\n\n**Requirements**:\n- Replace all \"file.py:123-456\"\
  \ patterns with function/class names or descriptive anchors\n- Examples:\n  - \"\
  tests/conftest.py:190-236\" → \"tests/conftest.py (`backup_project_config` fixture)\"\
  \n  - \"tests/conftest.py:239-353\" → \"tests/conftest.py (`mock_git_repo_check`\
  \ fixture)\"\n- Preserve semantic meaning while removing brittle line references\n\
  - Ensure documentation remains helpful and navigable\n- Update all instances identified\
  \ in audit subtask\n\n**References**: \n- Parent Task: features.bees-qon\n- File:\
  \ docs/architecture/testing.md\n- Depends on: features.bees-zjg (audit subtask)\n\
  \n**Acceptance**: All line number references replaced with stable identifiers; documentation\
  \ accuracy maintained; no \"file.py:123\" patterns remain."
up_dependencies:
- features.bees-zjg
down_dependencies:
- features.bees-v1q
parent: features.bees-qon
created_at: '2026-02-05T09:43:39.446311'
updated_at: '2026-02-05T09:58:46.953069'
status: completed
bees_version: '1.1'
---

**Context**: Remove stale line number references from docs/architecture/testing.md and replace with stable alternatives like function/class names or descriptive text that won't become outdated.

**Requirements**:
- Replace all "file.py:123-456" patterns with function/class names or descriptive anchors
- Examples:
  - "tests/conftest.py:190-236" → "tests/conftest.py (`backup_project_config` fixture)"
  - "tests/conftest.py:239-353" → "tests/conftest.py (`mock_git_repo_check` fixture)"
- Preserve semantic meaning while removing brittle line references
- Ensure documentation remains helpful and navigable
- Update all instances identified in audit subtask

**References**: 
- Parent Task: features.bees-qon
- File: docs/architecture/testing.md
- Depends on: features.bees-zjg (audit subtask)

**Acceptance**: All line number references replaced with stable identifiers; documentation accuracy maintained; no "file.py:123" patterns remain.
