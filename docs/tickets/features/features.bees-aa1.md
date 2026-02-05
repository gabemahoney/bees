---
id: features.bees-aa1
type: task
title: Create repo_context module
description: |
  Context: Need centralized, async-safe state management for repo_root instead of threading it through 24+ functions. This establishes the foundation for removing parameter threading by using Python's contextvars module for request-scoped state.

  What Needs to Change:
  - Create new file src/repo_context.py
  - Implement `_repo_root: contextvars.ContextVar[Path | None]` for async-safe storage
  - Implement `get_repo_root() -> Path` that raises RuntimeError if context not set
  - Implement `set_repo_root(path: Path) -> Token` for setting context
  - Implement `reset_repo_root(token: Token) -> None` for cleanup
  - Implement context manager `repo_root_context(path: Path)` using try/finally
  - Add clear error message when context not set: "repo_root not set in context. This is a bug - MCP entry points must call set_repo_root() before invoking core functions."

  Why: contextvars provides async-safe, request-scoped state with zero dependencies. This is the foundation that allows all downstream code to read repo_root without explicit parameter passing.

  Files: src/repo_context.py (new)

  Note: See parent Epic features.bees-nho for detailed implementation patterns and code examples.

  Success Criteria:
  - Module exists with all required functions
  - get_repo_root() raises clear error when context not set
  - Context manager properly handles async code
  - set_repo_root() returns token for cleanup
  - Module has type hints and docstrings
parent: features.bees-nho
children: ["features.bees-ab1", "features.bees-ab2", "features.bees-ab3"]
status: completed
priority: 0
created_at: '2026-02-04T19:00:00.000000'
updated_at: '2026-02-04T19:00:00.000000'
bees_version: '1.1'
---

Context: Need centralized, async-safe state management for repo_root instead of threading it through 24+ functions. This establishes the foundation for removing parameter threading by using Python's contextvars module for request-scoped state.

What Needs to Change:
- Create new file src/repo_context.py
- Implement `_repo_root: contextvars.ContextVar[Path | None]` for async-safe storage
- Implement `get_repo_root() -> Path` that raises RuntimeError if context not set
- Implement `set_repo_root(path: Path) -> Token` for setting context
- Implement `reset_repo_root(token: Token) -> None` for cleanup
- Implement context manager `repo_root_context(path: Path)` using try/finally
- Add clear error message when context not set: "repo_root not set in context. This is a bug - MCP entry points must call set_repo_root() before invoking core functions."

Why: contextvars provides async-safe, request-scoped state with zero dependencies. This is the foundation that allows all downstream code to read repo_root without explicit parameter passing.

Files: src/repo_context.py (new)

Success Criteria:
- Module exists with all required functions
- get_repo_root() raises clear error when context not set
- Context manager properly handles async code
- set_repo_root() returns token for cleanup
- Module has type hints and docstrings
