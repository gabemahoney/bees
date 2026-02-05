---
id: features.bees-uo6
type: subtask
title: Reduce is_valid_ticket_id tests to 5 essential cases
description: 'Refactor tests/test_id_utils.py TestIsValidTicketIdWithHive class to
  5 essential test cases:

  1. Valid ticket ID format (test_valid_hive_prefixed_ids)

  2. Invalid prefix format (test_invalid_hive_uppercase, test_invalid_hive_with_hyphen,
  test_invalid_hive_starting_with_number combined)

  3. Invalid suffix format (needs to be added - test invalid bees-xxx suffix)

  4. Missing separator (test_invalid_no_dot_separator, test_invalid_multiple_dots
  combined)

  5. Empty/None input (test_invalid_empty_hive)


  Delete redundant tests. Keep test coverage for core validation logic. Parent task:
  features.bees-zju'
down_dependencies:
- features.bees-79j
- features.bees-boa
- features.bees-3jf
parent: features.bees-zju
created_at: '2026-02-05T10:20:02.716021'
updated_at: '2026-02-05T10:27:30.275381'
status: completed
bees_version: '1.1'
---

Refactor tests/test_id_utils.py TestIsValidTicketIdWithHive class to 5 essential test cases:
1. Valid ticket ID format (test_valid_hive_prefixed_ids)
2. Invalid prefix format (test_invalid_hive_uppercase, test_invalid_hive_with_hyphen, test_invalid_hive_starting_with_number combined)
3. Invalid suffix format (needs to be added - test invalid bees-xxx suffix)
4. Missing separator (test_invalid_no_dot_separator, test_invalid_multiple_dots combined)
5. Empty/None input (test_invalid_empty_hive)

Delete redundant tests. Keep test coverage for core validation logic. Parent task: features.bees-zju
