---
id: features.bees-j2g
type: subtask
title: Add comprehensive docstring to conftest.py explaining mock patching strategy
description: 'Context: conftest.py needs a detailed module-level docstring explaining
  the entire mock patching approach used in the test suite.


  Requirements:

  - Add module-level docstring at top of conftest.py

  - Explain why source-level patching (shutil module) is used instead of import-level
  patching

  - Document the module reload mechanism and why it''s necessary

  - Explain the relationship between patching, reloading, and the needs_real_git_check
  marker

  - Provide examples of correct patching patterns (e.g., @patch(''bees.paths.shutil.rmtree''))

  - Provide examples of incorrect patterns (e.g., @patch(''shutil.rmtree''))

  - Include explanation of when to use needs_real_git_check marker


  Files: conftest.py


  Acceptance Criteria:

  - Docstring is comprehensive and covers all aspects of the patching strategy

  - Examples clearly demonstrate correct vs incorrect usage

  - Documentation explains the "why" behind each design decision'
parent: features.bees-k56
created_at: '2026-02-05T12:45:35.383982'
updated_at: '2026-02-05T15:55:53.940015'
status: completed
bees_version: '1.1'
---

Context: conftest.py needs a detailed module-level docstring explaining the entire mock patching approach used in the test suite.

Requirements:
- Add module-level docstring at top of conftest.py
- Explain why source-level patching (shutil module) is used instead of import-level patching
- Document the module reload mechanism and why it's necessary
- Explain the relationship between patching, reloading, and the needs_real_git_check marker
- Provide examples of correct patching patterns (e.g., @patch('bees.paths.shutil.rmtree'))
- Provide examples of incorrect patterns (e.g., @patch('shutil.rmtree'))
- Include explanation of when to use needs_real_git_check marker

Files: conftest.py

Acceptance Criteria:
- Docstring is comprehensive and covers all aspects of the patching strategy
- Examples clearly demonstrate correct vs incorrect usage
- Documentation explains the "why" behind each design decision
