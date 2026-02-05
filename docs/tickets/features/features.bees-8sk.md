---
id: features.bees-8sk
type: subtask
title: Update master_plan.md with mock patching architecture
description: 'Context: Document architectural decision to centralize mock patching
  at source module.


  Requirements:

  - Add section to master_plan.md documenting centralized mock patching pattern

  - Explain problem with import-site patching (silent failures when new imports added)

  - Document solution: patch at src.mcp_repo_utils.get_repo_root_from_path in conftest.py

  - Include design rationale and benefits (consistency, maintainability, reliability)


  Files: master_plan.md


  Acceptance: master_plan.md contains architectural documentation of centralized mock
  patching approach'
up_dependencies:
- features.bees-lbc
parent: features.bees-gjg
created_at: '2026-02-05T12:45:39.566693'
updated_at: '2026-02-05T12:53:08.470829'
status: completed
bees_version: '1.1'
---

Context: Document architectural decision to centralize mock patching at source module.

Requirements:
- Add section to master_plan.md documenting centralized mock patching pattern
- Explain problem with import-site patching (silent failures when new imports added)
- Document solution: patch at src.mcp_repo_utils.get_repo_root_from_path in conftest.py
- Include design rationale and benefits (consistency, maintainability, reliability)

Files: master_plan.md

Acceptance: master_plan.md contains architectural documentation of centralized mock patching approach
