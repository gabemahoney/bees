---
id: features.bees-y6w
type: epic
title: Create Shared Test Fixtures
description: "Foundation for eliminating 500+ lines of duplicate fixture code.\n\n\
  ## Requirements\n- Add 4 tiered fixtures to `conftest.py`:\n  - `bees_repo` - bare\
  \ repo with .bees directory\n  - `single_hive` - single 'backend' hive with config\n\
  \  - `multi_hive` - backend + frontend hives\n  - `hive_with_tickets` - single hive\
  \ with epic/task/subtask pre-created\n- Document each fixture's use case\n\n## Acceptance\
  \ Criteria\n- User runs `pytest` - all existing tests still pass\n- Agent creates\
  \ test demonstrating each fixture works correctly\n- Fixtures are documented in\
  \ conftest.py with clear usage examples\n\nSource: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md"
down_dependencies:
- features.bees-74p
- features.bees-c9p
children:
- features.bees-l71
- features.bees-m6i
- features.bees-u71
- features.bees-bx1
- features.bees-jc0
created_at: '2026-02-05T08:05:40.939627'
updated_at: '2026-02-05T10:35:18.557938'
priority: 2
status: completed
bees_version: '1.1'
---

Foundation for eliminating 500+ lines of duplicate fixture code.

## Requirements
- Add 4 tiered fixtures to `conftest.py`:
  - `bees_repo` - bare repo with .bees directory
  - `single_hive` - single 'backend' hive with config
  - `multi_hive` - backend + frontend hives
  - `hive_with_tickets` - single hive with epic/task/subtask pre-created
- Document each fixture's use case

## Acceptance Criteria
- User runs `pytest` - all existing tests still pass
- Agent creates test demonstrating each fixture works correctly
- Fixtures are documented in conftest.py with clear usage examples

Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md
