---
id: features.bees-lbc
type: subtask
title: Audit all test files for get_repo_root_from_path patches
description: 'Context: Need to identify all locations where get_repo_root_from_path
  is currently patched to ensure complete migration to source-module patching.


  Requirements:

  - Search all test files (tests/**/*.py) for patches of get_repo_root_from_path

  - Document current patch locations (file, line number, patch target)

  - Note whether patches use @patch decorator or patch.object context manager

  - Identify if any patches are at import sites vs source module


  Files: tests/**/*.py


  Acceptance: Complete list of all current get_repo_root_from_path patch locations
  documented'
down_dependencies:
- features.bees-yke
- features.bees-8sk
- features.bees-fqu
parent: features.bees-gjg
created_at: '2026-02-05T12:45:20.061613'
updated_at: '2026-02-05T12:50:57.411484'
status: completed
bees_version: '1.1'
---

Context: Need to identify all locations where get_repo_root_from_path is currently patched to ensure complete migration to source-module patching.

Requirements:
- Search all test files (tests/**/*.py) for patches of get_repo_root_from_path
- Document current patch locations (file, line number, patch target)
- Note whether patches use @patch decorator or patch.object context manager
- Identify if any patches are at import sites vs source module

Files: tests/**/*.py

Acceptance: Complete list of all current get_repo_root_from_path patch locations documented
