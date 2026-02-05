---
id: features.bees-2u5
type: subtask
title: Reduce normalize_hive_name tests to 4 essential cases
description: "**Context**: TestNormalizeHiveName class in tests/test_id_utils.py has\
  \ 13+ test methods covering redundant scenarios. Reduce to 4 essential test cases\
  \ as specified in parent Task features.bees-4tm.\n\n**Implementation**:\n- File:\
  \ tests/test_id_utils.py, lines 13-121\n- Keep/consolidate to exactly 4 test methods:\n\
  \  1. Standard normalization (lowercase, spaces→underscores, hyphens→underscores)\n\
  \  2. Special character removal (including unicode, numbers, complex cases)\n  3.\
  \ Empty/whitespace-only input (empty string, spaces, tabs, special-char-only strings)\n\
  \  4. Already-normalized input (no changes needed)\n- Delete redundant test methods\
  \ that cover edge cases already validated by the 4 essential tests\n- Ensure consolidated\
  \ tests use multiple assertions to maintain coverage breadth\n\n**Acceptance**:\
  \ \n- User runs `pytest tests/test_id_utils.py::TestNormalizeHiveName -v`\n- Exactly\
  \ 4 test methods in TestNormalizeHiveName class\n- All 4 tests pass\n- Coverage\
  \ for normalize_hive_name() remains unchanged (verify with `pytest --cov=src.id_utils\
  \ --cov-report=term-missing`)"
down_dependencies:
- features.bees-nzq
parent: features.bees-4tm
created_at: '2026-02-05T10:20:04.998477'
updated_at: '2026-02-05T10:23:46.579809'
status: completed
bees_version: '1.1'
---

**Context**: TestNormalizeHiveName class in tests/test_id_utils.py has 13+ test methods covering redundant scenarios. Reduce to 4 essential test cases as specified in parent Task features.bees-4tm.

**Implementation**:
- File: tests/test_id_utils.py, lines 13-121
- Keep/consolidate to exactly 4 test methods:
  1. Standard normalization (lowercase, spaces→underscores, hyphens→underscores)
  2. Special character removal (including unicode, numbers, complex cases)
  3. Empty/whitespace-only input (empty string, spaces, tabs, special-char-only strings)
  4. Already-normalized input (no changes needed)
- Delete redundant test methods that cover edge cases already validated by the 4 essential tests
- Ensure consolidated tests use multiple assertions to maintain coverage breadth

**Acceptance**: 
- User runs `pytest tests/test_id_utils.py::TestNormalizeHiveName -v`
- Exactly 4 test methods in TestNormalizeHiveName class
- All 4 tests pass
- Coverage for normalize_hive_name() remains unchanged (verify with `pytest --cov=src.id_utils --cov-report=term-missing`)
