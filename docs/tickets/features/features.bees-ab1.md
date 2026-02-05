---
id: features.bees-ab1
type: subtask
title: Implement repo_context.py with contextvars
description: |
  Context: Create the foundation module for async-safe repo_root state management using Python's contextvars.

  What to Implement:
  - Create src/repo_context.py
  - Import contextvars and pathlib
  - Create `_repo_root: ContextVar[Path | None] = ContextVar('repo_root', default=None)`
  - Implement `get_repo_root() -> Path` that calls `_repo_root.get()` and raises RuntimeError with message: "repo_root not set in context. This is a bug - MCP entry points must call set_repo_root() before invoking core functions."
  - Implement `set_repo_root(path: Path) -> Token` that calls `_repo_root.set(path)`
  - Implement `reset_repo_root(token: Token) -> None` that calls `_repo_root.reset(token)`
  - Implement context manager `repo_root_context(path: Path)` using try/finally pattern
  - Add type hints for all functions
  - Add docstrings explaining usage

  Success Criteria:
  - File created with all functions implemented
  - Type hints present
  - Error message matches specification
  - Context manager uses proper try/finally
parent: features.bees-aa1
status: completed
created_at: '2026-02-04T19:15:00.000000'
updated_at: '2026-02-04T19:15:00.000000'
bees_version: '1.1'
---

Context: Create the foundation module for async-safe repo_root state management using Python's contextvars.

What to Implement:
- Create src/repo_context.py
- Import contextvars and pathlib
- Create `_repo_root: ContextVar[Path | None] = ContextVar('repo_root', default=None)`
- Implement `get_repo_root() -> Path` that calls `_repo_root.get()` and raises RuntimeError with message: "repo_root not set in context. This is a bug - MCP entry points must call set_repo_root() before invoking core functions."
- Implement `set_repo_root(path: Path) -> Token` that calls `_repo_root.set(path)`
- Implement `reset_repo_root(token: Token) -> None` that calls `_repo_root.reset(token)`
- Implement context manager `repo_root_context(path: Path)` using try/finally pattern
- Add type hints for all functions
- Add docstrings explaining usage

Success Criteria:
- File created with all functions implemented
- Type hints present
- Error message matches specification
- Context manager uses proper try/finally
