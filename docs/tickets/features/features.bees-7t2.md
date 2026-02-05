---
id: features.bees-7t2
type: subtask
title: Document autouse fixtures (mock_git_repo_check, set_repo_root_context)
description: 'Context: The two autouse fixtures need better documentation explaining
  their relationship and when to opt-out.


  What to document:

  - Enhance mock_git_repo_check docstring with clear usage examples

  - Enhance set_repo_root_context docstring with usage examples

  - Explain how these two fixtures work together

  - Document the markers: @pytest.mark.needs_real_git_check and @pytest.mark.no_repo_context

  - Show examples of tests that need to opt-out of each fixture

  - Document the monkeypatch targets and why multiple patches are needed


  Files: tests/conftest.py (lines 30-131)


  Acceptance: Both docstrings include purpose, interaction explanation, opt-out markers
  with examples, and technical details about patching.'
parent: features.bees-m6i
created_at: '2026-02-05T08:09:43.697537'
updated_at: '2026-02-05T08:22:27.941314'
status: completed
bees_version: '1.1'
---

Context: The two autouse fixtures need better documentation explaining their relationship and when to opt-out.

What to document:
- Enhance mock_git_repo_check docstring with clear usage examples
- Enhance set_repo_root_context docstring with usage examples
- Explain how these two fixtures work together
- Document the markers: @pytest.mark.needs_real_git_check and @pytest.mark.no_repo_context
- Show examples of tests that need to opt-out of each fixture
- Document the monkeypatch targets and why multiple patches are needed

Files: tests/conftest.py (lines 30-131)

Acceptance: Both docstrings include purpose, interaction explanation, opt-out markers with examples, and technical details about patching.
