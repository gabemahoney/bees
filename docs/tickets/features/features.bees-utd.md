---
id: features.bees-utd
type: epic
title: Reduce Over-Testing of Simple Functions
description: 'Remove redundant test coverage for trivial functions, improving test
  suite maintainability.


  ## Requirements

  - Reduce `normalize_hive_name` tests from 13+ to 4 essential cases

  - Reduce `is_valid_ticket_id` tests to 5 essential cases

  - Reduce port validation tests to 2 essential cases

  - Delete duplicate tests in test_config.py and test_hive_utils.py


  ## Acceptance Criteria

  - User runs `pytest tests/test_id_utils.py` - passes with 4 normalize_hive_name
  tests

  - User runs `pytest --cov=src` - coverage remains unchanged

  - Agent creates PR showing ~300 line reduction with no lost coverage


  Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md'
labels:
- not-started
status: open
created_at: '2026-02-05T08:05:38.256465'
updated_at: '2026-02-05T08:05:38.256471'
bees_version: '1.1'
priority: 2
---

Remove redundant test coverage for trivial functions, improving test suite maintainability.

## Requirements
- Reduce `normalize_hive_name` tests from 13+ to 4 essential cases
- Reduce `is_valid_ticket_id` tests to 5 essential cases
- Reduce port validation tests to 2 essential cases
- Delete duplicate tests in test_config.py and test_hive_utils.py

## Acceptance Criteria
- User runs `pytest tests/test_id_utils.py` - passes with 4 normalize_hive_name tests
- User runs `pytest --cov=src` - coverage remains unchanged
- Agent creates PR showing ~300 line reduction with no lost coverage

Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/0_test_cleanup/test_cleanup_plan.md
