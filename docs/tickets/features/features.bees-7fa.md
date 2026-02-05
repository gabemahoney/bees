---
id: features.bees-7fa
type: subtask
title: Document needs_real_git_check marker usage in conftest.py
description: "Context: Developers need to understand when and how to use the marker.\n\
  \nRequirements:\n- Add docstring or comment block in conftest.py explaining:\n \
  \ - When to use @pytest.mark.needs_real_git_check\n  - What behavior changes when\
  \ marker is applied (skips git mock patching)\n  - Example usage\n\nFiles: conftest.py\n\
  \nAcceptance: Clear documentation exists showing marker purpose and usage pattern"
parent: features.bees-27y
status: open
created_at: '2026-02-05T12:45:34.175452'
updated_at: '2026-02-05T12:45:34.175455'
bees_version: '1.1'
---

Context: Developers need to understand when and how to use the marker.

Requirements:
- Add docstring or comment block in conftest.py explaining:
  - When to use @pytest.mark.needs_real_git_check
  - What behavior changes when marker is applied (skips git mock patching)
  - Example usage

Files: conftest.py

Acceptance: Clear documentation exists showing marker purpose and usage pattern
