# Test Categorization for test_mcp_server.py Split

## Summary Statistics

- **Total tests**: 155
- **Lifecycle tests**: 25 tests (~371 lines)
- **Scan/Validate tests**: 38 tests (~1,260 lines)
- **Remaining tool tests**: 92 tests (~1,491 lines)

## Category 1: Lifecycle Tests (→ test_mcp_server_lifecycle.py)

### TestMCPServerInitialization
- test_server_instance_exists (line 33)
- test_server_name_configuration (line 38)
- test_server_has_required_attributes (line 42)

### TestServerLifecycle
- test_start_server_success (line 52)
- test_stop_server_success (line 61)
- test_start_stop_cycle (line 73)
- test_start_server_logs_messages (line 88)
- test_stop_server_logs_messages (line 96)

### TestHealthCheck
- test_health_check_when_server_running (line 108)
- test_health_check_when_server_stopped (line 121)
- test_health_check_returns_dict (line 132)

### TestToolRegistration
- test_health_check_tool_registered (line 145)
- test_create_ticket_tool_registered (line 151)
- test_update_ticket_tool_registered (line 156)
- test_delete_ticket_tool_registered (line 160)
- test_create_ticket_implementation_response (line 164)
- test_create_ticket_validates_type (line 201)
- test_create_ticket_validates_epic_parent (line 208)
- test_create_ticket_validates_subtask_parent (line 238)

### TestErrorHandling
- test_start_server_exception_handling (line 273)
- test_stop_server_exception_handling (line 284)

### TestServerConfiguration
- test_server_has_version (line 294)
- test_server_has_name (line 300)

### TestModuleIntegration
- test_all_modules_import_successfully (line 3085)
- test_mcp_server_imports_all_modules (line 3101)
- test_tool_registration_count (line 3130)
- test_delegated_functions_are_callable (line 3158)

**Total**: 25 tests, ~371 lines

---

## Category 2: Scan/Validate Tests (→ test_mcp_scan_validate.py)

### TestGetRepoRoot
- test_get_repo_root_success (line 737)
- test_get_repo_root_at_root (line 751)
- test_get_repo_root_not_in_repo (line 760)

### TestValidateHivePath
- test_validate_hive_path_valid_absolute_path (line 773)
- test_validate_hive_path_with_trailing_slash (line 787)
- test_validate_hive_path_relative_path_fails (line 802)
- test_validate_hive_path_nonexistent_parent_fails (line 812)
- test_validate_hive_path_outside_repo_fails (line 828)
- test_validate_hive_path_at_repo_root (line 841)
- test_validate_hive_path_deeply_nested (line 851)
- test_validate_hive_path_error_messages (line 864)

### TestScanForHiveConfigAutoUpdate
- test_scan_for_hive_updates_config_with_stale_path (line 910)
- test_scan_for_hive_handles_missing_config (line 949)
- test_scan_for_hive_updates_only_target_hive (line 972)
- test_scan_for_hive_logs_config_update (line 1010)
- test_scan_for_hive_handles_config_write_failure (line 1044)

### TestScanForHiveSecurity
- test_scan_for_hive_respects_depth_limit (line 1096)
- test_scan_for_hive_finds_hive_within_depth_limit (line 1119)
- test_scan_for_hive_depth_limit_boundary (line 1142)

### TestScanForHiveConfigOptimization
- test_scan_for_hive_accepts_config_parameter (line 1183)
- test_scan_for_hive_uses_provided_config (line 1210)
- test_scan_for_hive_empty_config_parameter (line 1249)
- test_scan_for_hive_config_with_empty_hives (line 1271)
- test_scan_for_hive_loads_from_disk_when_config_not_provided (line 1293)

### TestScanForHiveBugFixes
- test_scan_for_hive_config_none_handling (line 1338)
- test_scan_for_hive_config_empty_hives (line 1359)
- test_scan_for_hive_early_return_behavior (line 1382)
- test_scan_for_hive_beesconfig_type_handling (line 1410)

### TestScanForHiveFileVsDirectory
- test_scan_for_hive_skips_file_marker (line 1459)
- test_scan_for_hive_returns_none_when_only_file_marker (line 1486)

### TestScanForHiveExceptionHandling
- test_scan_for_hive_handles_ioerror_on_config_update (line 1516)
- test_scan_for_hive_handles_json_decode_error_on_config_load (line 1555)
- test_scan_for_hive_handles_attribute_error_on_config_access (line 1594)
- test_scan_for_hive_does_not_catch_programming_errors (line 1636)
- test_scan_for_hive_exception_handling_specificity (line 1664)

### TestScanForHiveErrorPropagation
- test_scan_for_hive_raises_ioerror_on_config_save_failure (line 1722)
- test_scan_for_hive_raises_json_decode_error_on_config_failure (line 1763)
- test_scan_for_hive_logs_before_raising (line 1804)

### TestScanForHiveConfigHandling
- test_scan_for_hive_with_config_none_loads_from_disk (line 1867)
- test_scan_for_hive_with_empty_hives_dict (line 1897)
- test_scan_for_hive_with_populated_hives (line 1923)
- test_scan_for_hive_registered_hives_set_populated_correctly (line 1966)

**Total**: 38 tests, ~1,260 lines (NOTE: Much larger than Epic's ~300 estimate!)

---

## Category 3: Remaining Tool Tests (→ test_mcp_server.py)

### TestUpdateTicket
- test_update_ticket_basic_fields (line 311)
- test_update_ticket_nonexistent (line 356)
- test_update_ticket_empty_title (line 364)
- test_update_ticket_add_parent (line 379)
- test_update_ticket_remove_parent (line 406)
- test_update_ticket_add_children (line 441)
- test_update_ticket_remove_children (line 474)
- test_update_ticket_add_dependencies (line 511)
- test_update_ticket_remove_dependencies (line 548)
- test_update_ticket_nonexistent_parent (line 586)
- test_update_ticket_nonexistent_child (line 598)
- test_update_ticket_nonexistent_dependency (line 610)
- test_update_ticket_circular_dependency (line 625)
- test_update_ticket_partial_update (line 642)
- test_update_ticket_bidirectional_consistency (line 681)

### TestColonizeHiveMCPIntegration
- test_colonize_hive_success_case (line 2017)
- test_colonize_hive_creates_marker (line 2038)
- test_colonize_hive_invalid_path_not_absolute (line 2058)
- test_colonize_hive_path_does_not_exist (line 2065)
- test_colonize_hive_path_outside_repo (line 2080)
- test_colonize_hive_duplicate_name (line 2097)
- test_colonize_hive_invalid_name_empty (line 2114)
- test_colonize_hive_registers_in_config (line 2124)
- test_colonize_hive_name_normalization (line 2141)

### TestColonizeHiveMCPUnit
- test_colonize_hive_tool_callable (line 2165)
- test_colonize_hive_accepts_name_and_path_parameters (line 2171)
- test_colonize_hive_parameter_validation_empty_name (line 2182)
- test_colonize_hive_parameter_validation_invalid_path_format (line 2193)
- test_colonize_hive_success_response_structure (line 2200)
- test_colonize_hive_error_response_raises_value_error (line 2217)
- test_colonize_hive_wraps_core_function (line 2225)
- test_colonize_hive_propagates_core_function_errors (line 2248)
- test_colonize_hive_handles_unexpected_exceptions (line 2267)

### TestColonizeHiveMCPErrorCases
- test_colonize_hive_filesystem_error_eggs_creation (line 2304)
- test_colonize_hive_filesystem_error_evicted_creation (line 2323)
- test_colonize_hive_error_writing_identity_file (line 2342)
- test_colonize_hive_config_write_failure (line 2361)

### TestParseTicketId
- test_parse_hive_prefixed_id (line 2378)
- test_parse_legacy_id_without_dot (line 2384)
- test_parse_id_with_multiple_dots (line 2390)
- test_parse_id_with_underscore_hive (line 2396)
- test_parse_id_none_raises_error (line 2402)
- test_parse_id_empty_string_raises_error (line 2407)
- test_parse_id_whitespace_only_raises_error (line 2412)
- test_parse_id_returns_tuple (line 2417)
- test_parse_id_backward_compatibility (line 2423)
- test_parse_id_complex_hive_names (line 2430)
- test_parse_id_complex_base_ids (line 2443)
- test_parse_id_edge_case_dot_at_end (line 2455)
- test_parse_id_edge_case_dot_at_start (line 2461)

### TestParseHiveFromTicketId (DUPLICATE CLASS WARNING!)
- test_parse_hive_with_valid_prefixed_id (line 2471)
- test_parse_hive_with_frontend_id (line 2476)
- test_parse_hive_with_malformed_id_no_dot (line 2481)
- test_parse_hive_with_multi_dot_id (line 2486)
- test_parse_hive_with_underscore_hive (line 2491)
- test_parse_hive_with_hyphen_hive (line 2496)
- test_parse_hive_returns_none_for_legacy_format (line 2501)
- test_extracts_hive_prefix_from_valid_id (line 2624)
- test_returns_none_for_malformed_id_no_dot (line 2630)
- test_handles_multiple_dots_correctly (line 2636)
- test_handles_empty_prefix (line 2642)
- test_handles_empty_suffix (line 2648)

### TestUpdateTicketHiveParsing
- test_update_ticket_with_valid_prefixed_id (line 2567)
- test_update_ticket_with_malformed_id_raises_error (line 2581)
- test_update_ticket_with_unknown_hive_raises_error (line 2592)
- test_update_ticket_routes_to_correct_hive (line 2603)

### TestListHives
- test_list_hives_returns_all_hives_from_config (line 2686)
- test_list_hives_returns_empty_list_when_no_config (line 2730)
- test_list_hives_returns_empty_list_when_no_hives (line 2741)
- test_list_hives_returns_correct_fields (line 2756)
- test_list_hives_handles_exception (line 2787)
- test_list_hives_with_single_hive (line 2801)
- test_list_hives_with_many_hives (line 2824)

### TestAbandonHive
- test_abandon_hive_removes_from_config (line 2864)
- test_abandon_hive_preserves_files (line 2888)
- test_abandon_hive_returns_error_for_nonexistent (line 2912)
- test_abandon_hive_returns_success_message (line 2922)
- test_abandon_hive_handles_normalized_name (line 2935)
- test_abandon_hive_handles_display_name (line 2948)
- test_abandon_hive_returns_path (line 2960)
- test_abandon_hive_with_multiple_hives (line 2972)
- test_abandon_hive_handles_last_hive (line 3001)
- test_abandon_hive_normalizes_hive_name (line 3019)
- test_abandon_hive_preserves_eggs_directory (line 3031)
- test_abandon_hive_preserves_evicted_directory (line 3045)
- test_abandon_hive_response_structure (line 3059)

**Total**: 92 tests, ~1,491 lines

---

## Verification

- ✅ Total test count: 25 + 38 + 92 = **155 tests** (matches expected)
- ✅ All tests categorized exactly once
- ⚠️ Line count distribution differs from Epic estimates:
  - Epic estimate: 400 + 300 + 1,600 = 2,300 lines (target file is 3,178 lines)
  - Actual: 371 + 1,260 + 1,491 = 3,122 lines
  - **Scan/Validate category is much larger than estimated (1,260 vs 300)**

## Notes

1. **Duplicate TestParseHiveFromTicketId class**: Lines 2468 and 2621 both define this class. This should be fixed during migration.
2. **Scan/Validate line count**: The Epic underestimated scan_for_hive() test complexity. The actual test coverage is ~4x larger than estimated.
3. **Line ranges**:
   - Lifecycle: 30-305 + 3078-3178
   - Scan/Validate: 734-2002
   - Remaining: 307-732 + 2004-3076
