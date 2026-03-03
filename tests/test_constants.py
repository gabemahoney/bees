"""
Centralized test constants for the Bees ticket management system.

This module provides standardized test data used across all test files to ensure
consistency and eliminate duplication. Constants are organized by category for
easy reference and maintenance.

Usage:
    from tests.test_constants import HIVE_TEST, TITLE_TEST_BEE, STATUS_OPEN

Organization:
    - GUID Examples: Pre-built GUID constants for tier-specific tests
    - Hive Names: Standard hive identifiers for tests
    - Title Constants: Descriptive titles for test tickets
    - Status Constants: Ticket status values
    - Ticket Type Constants: Valid ticket type identifiers
    - Owner Constants: User email addresses for ownership tests
    - Result Status Constants: API/function result status values
"""


# ============================================================================
# GUID Examples — exactly 32 chars, all from ID_CHARSET, prefix = valid short_id
# ============================================================================
GUID_EXAMPLE_BEE = "abc123456789abcdefghjk1234567891"  # bee short_id "abc" (3 chars) + 29 filler
GUID_EXAMPLE_T1 = "abcde23456789abcdefghj1234567891"  # t1 short_id "abc.de" → stripped seed "abcde" (5 chars) + 27 filler
GUID_EXAMPLE_T2 = "abcdefg3456789abcdefgh1234567891"  # t2 short_id "abc.de.fg" → stripped seed "abcdefg" (7 chars) + 25 filler

# ============================================================================
# Hive Names
# ============================================================================
HIVE_TEST = "test_hive"  # Primary standard hive for most tests
HIVE_BACKEND = "backend"  # For multi-hive tests
HIVE_FRONTEND = "frontend"  # For multi-hive tests
HIVE_DEFAULT = "default"  # For default hive tests

# ============================================================================
# Title Constants
# ============================================================================
TITLE_TEST_BEE = "Test Bee"
TITLE_TEST_EPIC = "Test Epic"  # Used in index generator tests
TITLE_TEST_TASK = "Test Task"
TITLE_TEST_SUBTASK = "Test Subtask"
TITLE_PARENT_BEE = "Parent Bee"  # For relationship debugging
TITLE_CHILD_TASK = "Child Task"  # For relationship debugging

# ============================================================================
# Status Constants
# ============================================================================
# Note: Simple status strings like "open", "in_progress", "completed" should be inlined in tests
# per test_review_guide.md. Only keep constants for complex patterns or values used 5+ places

# ============================================================================
# Ticket Type Constants
# ============================================================================
# Note: Simple type strings like "bee", "t1", "t2" should be inlined in tests per test_review_guide.md
# Only keep constants for complex patterns or values used 5+ places

# ============================================================================
# Owner Constants
# ============================================================================
OWNER_USER = "user@example.com"
OWNER_ALICE = "alice@example.com"
OWNER_BOB = "bob@example.com"
OWNER_TESTER = "tester"

# ============================================================================
# Result Status Constants
# ============================================================================
RESULT_STATUS_SUCCESS = "success"
RESULT_STATUS_ERROR = "error"

# ============================================================================
# Ticket ID Constants
# ============================================================================
TICKET_ID_TEST_BEE = "b.abc"  # Standard test bee ID
TICKET_ID_T1 = "t1.abc.de"  # Standard test t1 (task) ID (period-separated: 3+2 chars)
TICKET_ID_T2 = "t2.abc.de.fg"  # Standard test t2 (subtask) ID (period-separated: 3+2+2 chars)
TICKET_ID_PARENT_BEE = "b.xyz"  # For parent/child relationship tests
TICKET_ID_TEST_TASK = "t1.tk1.1a"  # Standard test task ID (period-separated: 3+2 chars)
TICKET_ID_MALFORMED = "no-dot-format"  # Missing dot separator for error tests
TICKET_ID_UNKNOWN_HIVE = "x.xyz"  # Unknown type prefix for error tests
TICKET_FILE_TEST_BEE = "b.abc.md"  # Standard ticket filename
TICKET_ID_NONEXISTENT = "b.zzz"  # For testing nonexistent ticket references

# Index generator test IDs
TICKET_ID_SUBTASK_1 = "t2.s12.34.ab"
TICKET_FILE_EPIC_1 = "b.ep1.md"
TICKET_FILE_EPIC_2 = "b.ep2.md"
TICKET_FILE_TASK_1 = "t1.xyz.1a.md"
TICKET_FILE_SUBTASK_1 = "t2.s12.34.ab.md"

# Graph executor test IDs (add to existing constants section)
TICKET_ID_EP1 = "b.ep1"
TICKET_ID_EP2 = "b.ep2"
TICKET_ID_TK1 = "t1.tk1.1a"
TICKET_ID_TK2 = "t1.tk2.2a"
TICKET_ID_TK3 = "t1.tk3.3a"
TICKET_ID_ST1 = "t2.st1.11.ab"
TICKET_ID_ST2 = "t2.st2.22.ab"
TICKET_ID_ST3 = "t2.st3.33.ab"
TICKET_ID_XXX = "b.xxx"  # For nonexistent ticket tests
TICKET_ID_YYY = "b.yyy"  # For nonexistent ticket tests
TICKET_ID_ORPHAN = "b.orp"
TICKET_ID_LONELY = "b.mon"
TICKET_ID_INDEPENDENT = "b.ind"
TICKET_ID_ISOLATED = "b.iso"
TICKET_ID_LEAF = "b.fea"
TICKET_ID_ROOT = "b.roo"
TICKET_ID_TERMINAL = "b.ter"

# CLI test IDs
TICKET_ID_ABC = "b.abc"
TICKET_ID_XYZ = "b.xyz"

# ============================================================================
# ID Validation and Format Test IDs
# ============================================================================
# Valid format examples for testing
TICKET_ID_VALID_BEE_MIXED = "b.anx"  # Bee ID (all lowercase)
TICKET_ID_VALID_T3_CAPS = "t3.x4f.2a.bc.de"  # T3 ID (9-char short_id, period-separated: 3+2+2+2)
TICKET_ID_VALID_BEE_R8P = "b.r8p"  # Bee ID variant
TICKET_ID_VALID_BEE_X4F = "b.x4f"  # Bee ID variant
TICKET_ID_VALID_T1_R8P2 = "t1.r8p.2a"  # Task ID variant (period-separated: 3+2 chars)

# Canonical bee ID for reuse across tests
TICKET_ID_CASE_AMX_LOWER = "b.amx"

# Invalid format examples for error testing
TICKET_ID_INVALID_TOO_SHORT = "b.am"  # Too short (2 chars, bee needs 3)
TICKET_ID_INVALID_TOO_LONG = "b.amx9"  # Too long (4 chars, bee needs 3)
TICKET_ID_INVALID_T1_SHORT = "t1.x4f"  # Task too short (3 chars, t1 needs 5 non-period chars)
TICKET_ID_INVALID_T1_LONG = "t1.abcdef"  # Task malformed (6 chars, no period-separation)
TICKET_ID_INVALID_T2_SHORT = "t2.r8p2"  # Subtask too short (4 chars, t2 needs 7 non-period chars)
TICKET_ID_INVALID_OLD_T1 = "t1.abcde"  # Old concatenated format (no period-separation) - rejected by new validator
TICKET_ID_INVALID_OLD_T2 = "t2.abcdefg"  # Old concatenated format (no period-separation) - rejected by new validator

# Disallowed characters for validation testing
TICKET_ID_INVALID_ZERO = "b.a0x"  # Contains zero
TICKET_ID_INVALID_O_UPPER = "b.aOx"  # Contains uppercase O
TICKET_ID_INVALID_O_LOWER = "b.aox"  # Contains lowercase o (now valid in ID_CHARSET — update tests if needed)
TICKET_ID_INVALID_I_UPPER = "b.aIx"  # Contains uppercase I
TICKET_ID_INVALID_I_LOWER = "b.aix"  # Contains lowercase i (now valid in ID_CHARSET — update tests if needed)
TICKET_ID_INVALID_L_UPPER = "b.aLx"  # Contains uppercase L
TICKET_ID_INVALID_L_LOWER = "b.alx"  # Contains lowercase l (excluded from ID_CHARSET)

# Malformed IDs for error handling tests
TICKET_ID_INVALID_SHORT_ID = "b.1"  # Too short
TICKET_ID_INVALID_SINGLE_CHAR = "b.a"  # Single character
TICKET_ID_INVALID_UPPER_PREFIX = "b.up"  # Too short (2 chars)
TICKET_ID_INVALID_TOOLONG = "b.tooaong"  # Way too long (7 chars, bee needs 3)
TICKET_ID_INVALID_NOPE = "b.nope"  # Invalid length (4 chars)

# ============================================================================
# Reader and Legacy Format Test IDs
# ============================================================================
TICKET_ID_LEGACY_BEE = "b.25a"  # Legacy bee ID format
TICKET_ID_LEGACY_TASK = "t1.jty.ab"  # Legacy task ID format (period-separated: 3+2 chars)
TICKET_ID_LEGACY_SUBTASK = "t2.xyz.ab.cd"  # Legacy subtask ID format (period-separated: 3+2+2 chars)
TICKET_ID_LEGACY_BEE_ALT = "b.9pw"  # Alternative legacy bee ID

# ============================================================================
# Linter Relationship Test IDs
# ============================================================================
TICKET_ID_LINTER_DUP = "b.dup"  # For duplicate ID testing
TICKET_ID_LINTER_VALID = "b.van"  # For validation testing
TICKET_ID_LINTER_TASK_MAIN = "t1.xyz.ab"  # Main task for linter tests (period-separated: 3+2 chars)
TICKET_ID_LINTER_SUBTASK_MAIN = "t2.1a2.b3.cd"  # Main subtask for linter tests (period-separated: 3+2+2 chars)

# Parent-child relationship testing
TICKET_ID_LINTER_CHILD1 = "t1.1a2.bc"  # Child task 1 (period-separated: 3+2 chars)
TICKET_ID_LINTER_CHILD2 = "t1.2c3.de"  # Child task 2 (period-separated: 3+2 chars)
TICKET_ID_LINTER_CHILD3 = "t1.3e4.fg"  # Child task 3 (period-separated: 3+2 chars)
TICKET_ID_LINTER_PARENT_TASK = "t1.tsk.ab"  # Parent task (period-separated: 3+2 chars)
TICKET_ID_LINTER_CHILD_SUBTASK = "t2.sub.ab.cd"  # Child subtask (period-separated: 3+2+2 chars)

# Dependency relationship testing
TICKET_ID_LINTER_DEP_A = "t1.aaa.bc"  # Dependency A (period-separated: 3+2 chars)
TICKET_ID_LINTER_DEP_B = "t1.bbb.cd"  # Dependency B (period-separated: 3+2 chars)

# Hierarchy validation testing
TICKET_ID_LINTER_TIER1 = "t1.t1a.bc"  # Tier 1 task (period-separated: 3+2 chars)
TICKET_ID_LINTER_TIER2 = "t1.t2a.bc"  # Tier 2 task (invalid hierarchy) (period-separated: 3+2 chars)
TICKET_ID_LINTER_TIER3 = "t1.t3a.bc"  # Tier 3 task (invalid hierarchy) (period-separated: 3+2 chars)

# Dangling reference detection testing (IDs that must never exist in any test hive)
DANGLING_BEE_ID = "b.zzz"   # Non-existent bee ID for dangling detection tests

# ============================================================================
# Index Generator Test IDs
# ============================================================================
TICKET_ID_INDEX_BEE_BACKEND1 = "b.be1"  # Backend bee 1
TICKET_ID_INDEX_BEE_BACKEND2 = "b.be2"  # Backend bee 2
TICKET_ID_INDEX_BEE_FRONTEND = "b.fe2"  # Frontend bee
TICKET_ID_INDEX_BEE_DEFAULT1 = "b.de3"  # Default hive bee 1
TICKET_ID_INDEX_BEE_DEFAULT2 = "b.de9"  # Default hive bee 2
TICKET_ID_INDEX_BEE_MULTI = "b.bac"  # Multi-hive test bee
TICKET_ID_INDEX_TASK_FRONTEND = "t1.fxy.za"  # Frontend task (period-separated: 3+2 chars)
TICKET_ID_INDEX_TASK_TEST = "t1.ts9.ab"  # Test task (period-separated: 3+2 chars)
TICKET_ID_INDEX_SUBTASK_TEST = "t2.sb9.ab.cd"  # Test subtask (period-separated: 3+2+2 chars)

# Index generator specific test cases
TICKET_ID_INDEX_BABC1 = "b.ba1"  # Backend ABC bee variant
TICKET_ID_INDEX_TASK_TS1 = "t1.ts1.ab"  # Index test task TS1 (period-separated: 3+2 chars)
TICKET_ID_INDEX_SUBTASK_SB1 = "t2.sb1.ab.cd"  # Index test subtask SB1 (period-separated: 3+2+2 chars)
TICKET_ID_INDEX_TASK_FXYZ9 = "t1.fxy.z9"  # Index test task FXYZ9 (period-separated: 3+2 chars)
TICKET_ID_INDEX_SUBTASK_B123A = "t2.b12.3a.bc"  # Index test subtask B123A (period-separated: 3+2+2 chars)

# Hierarchy rendering test IDs (4-tier chain)
TICKET_ID_INDEX_HIER_BEE = "b.hc1"  # Bee root for hierarchy chain test
TICKET_ID_INDEX_HIER_T1 = "t1.hc1.ab"  # t1 (Epic) child of HIER_BEE (period-separated: 3+2 chars)
TICKET_ID_INDEX_HIER_T2 = "t2.hc1.ab.cd"  # t2 (Task) child of HIER_T1 (period-separated: 3+2+2 chars)
TICKET_ID_INDEX_HIER_T3 = "t3.hc1.ab.cd.ef"  # t3 (Subtask) child of HIER_T2 (period-separated: 3+2+2+2 chars)

# Bees-only scenario test IDs
TICKET_ID_INDEX_BEES_ONLY_1 = "b.bn1"  # Bees-only hive bee 1
TICKET_ID_INDEX_BEES_ONLY_2 = "b.bn2"  # Bees-only hive bee 2

# Unparented ticket test IDs
TICKET_ID_INDEX_UNPARENTED = "b.up1"  # Bee with phantom parent reference
TICKET_ID_INDEX_PHANTOM_PARENT = "b.phn"  # Non-existent parent ID for unparented test

# ============================================================================
# Mermaid Graph Test IDs
# ============================================================================
TICKET_ID_MERMAID_BEE_A = "b.ma1"  # Bee A for dep graph tests
TICKET_ID_MERMAID_BEE_B = "b.mb1"  # Bee B (depends on Bee A)
TICKET_ID_MERMAID_EPIC_A = "t1.mea.1a"  # Epic A for dep graph tests (period-separated: 3+2 chars)
TICKET_ID_MERMAID_EPIC_B = "t1.meb.1a"  # Epic B (depends on Epic A) (period-separated: 3+2 chars)
TICKET_ID_MERMAID_ORPHAN_DEP = "b.mzz"  # Non-existent ticket for orphan dep tests
TICKET_ID_MERMAID_CIRC_A = "b.ca1"  # First bee in circular dep pair
TICKET_ID_MERMAID_CIRC_B = "b.cb1"  # Second bee in circular dep pair
MERMAID_TEST_TITLE = "Mermaid Test"  # Shared title for mermaid test tickets

# ============================================================================
# MCP Server Test IDs
# ============================================================================
TICKET_ID_MCP_TASK_A = "t1.tk1.ab"  # MCP task A (period-separated: 3+2 chars)
TICKET_ID_MCP_TASK_B = "t1.tk2.ab"  # MCP task B (period-separated: 3+2 chars)
TICKET_ID_MCP_SUBTASK = "t2.st1.ab.cd"  # MCP subtask (period-separated: 3+2+2 chars)
TICKET_ID_MCP_BEE_VARIANT = "b.ab1"  # MCP bee variant
TICKET_ID_MCP_TASK_VARIANT = "t1.xyz.9a"  # MCP task variant (period-separated: 3+2 chars)
TICKET_ID_MCP_SUBTASK_VARIANT = "t2.amx.ab.cd"  # MCP subtask variant (period-separated: 3+2+2 chars)

# MCP rename hive test IDs
TICKET_ID_MCP_RENAME_TASK1 = "t1.abc.1a"  # Rename test task 1 (period-separated: 3+2 chars)
TICKET_ID_MCP_RENAME_TASK2 = "t1.xyz.2a"  # Rename test task 2 (period-separated: 3+2 chars)
TICKET_ID_MCP_RENAME_TASK3 = "t1.def.3a"  # Rename test task 3 (frontend) (period-separated: 3+2 chars)

# ============================================================================
# Path Resolution Test IDs
# ============================================================================
TICKET_ID_PATH_BAD_YAML = "b.bad"  # Invalid YAML
TICKET_ID_PATH_NO_TYPE = "b.nty"  # Missing type field
TICKET_ID_PATH_NO_VERSION = "b.nvr"  # Missing schema_version

# ============================================================================
# Test Main Linter Test Data
# ============================================================================
TICKET_ID_MAIN_LINTER_A = "b.dab"  # Main test linter ID A
TICKET_ID_MAIN_LINTER_B = "b.dxy"  # Main test linter ID B

# ============================================================================
# ============================================================================
# Helper Function Example IDs
# ============================================================================
TICKET_ID_HELPER_TASK_DEP = "t1.def.1a"  # Helper task dependency example (period-separated: 3+2 chars)
TICKET_ID_HELPER_TASK_JKL = "t1.jkm.1a"  # Helper task JKL example (period-separated: 3+2 chars)
TICKET_ID_HELPER_TASK_XYZ1 = "t1.xyz.1a"  # Helper task XYZ1 example (period-separated; corresponds to TICKET_FILE_TASK_1)
TICKET_ID_HELPER_BEE_GHI = "b.ghi"  # Helper bee GHI example (from doc examples)

# ============================================================================
# Egg Field Test Constants
# ============================================================================
EGG_URL = "https://example.com/spec.md"
EGG_GUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
EGG_NULL = None
EGG_OBJECT = {"type": "spec", "url": "https://example.com/spec.md", "version": "1.0"}
EGG_ARRAY = ["https://example.com/spec1.md", "https://example.com/spec2.md"]

# ============================================================================
# Per-Hive Child Tier Config Constants
# ============================================================================
# Tier configs for per-hive child_tiers testing (three-level resolution)

# Hive-level overrides (stored inside hive entries)
HIVE_TIER_EPICS = {"t1": ["Epic", "Epics"], "t2": ["Task", "Tasks"]}
HIVE_TIER_BEES_ONLY = {}  # Explicit empty = bees-only, stops fallthrough
HIVE_TIER_SINGLE = {"t1": ["Story", "Stories"]}
HIVE_TIER_DEEP = {"t1": ["Phase", "Phases"], "t2": ["Step", "Steps"], "t3": ["Action", "Actions"]}

# Global-level child_tiers (distinct three-tier config for global vs scope tests)
GLOBAL_TIER_DEFAULT = {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"], "t3": ["Work Item", "Work Items"]}

# Scope-level defaults (the fallback when hive has no child_tiers key)
SCOPE_TIER_DEFAULT = {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]}
SCOPE_TIER_SINGLE = {"t1": ["Task", "Tasks"]}

# Hive names for per-hive tier tests
HIVE_FEATURES = "features"
HIVE_BUGS = "bugs"
HIVE_DOCS = "docs"

# --- Move Bee Tests ---
HIVE_DESTINATION = "hive_dest"  # Destination hive for move-bee tests
HIVE_OTHER_SCOPE = "hive_other_scope"  # Hive registered under a different scope key
TICKET_ID_MOVE_BEE_1 = "b.mv1"  # Primary move-bee test ticket
TICKET_ID_MOVE_BEE_2 = "b.mv2"  # Child-ticket move-bee test ticket

# ============================================================================
# Corruption Handling Test IDs
# ============================================================================
TICKET_ID_CORRUPT_BEE = "b.zx9"    # Valid bee ID for corruption handling tests
TICKET_ID_CORRUPT_TASK = "t1.ab3.ca"  # Valid t1 ID for corruption handling tests (period-separated: 3+2 chars)

# ============================================================================
# Batch Update Tag Constants
# ============================================================================
TAG_BATCH_FOO = "batch-foo"
TAG_BATCH_BAR = "batch-bar"
TAG_BATCH_BAZ = "batch-baz"

# ============================================================================
# Tag Constants
# ============================================================================
TAG_ALPHA = "label-alpha"
TAG_BETA = "label-beta"
TAG_GAMMA = "label-gamma"
TAG_DELTA = "label-delta"

# ============================================================================
# STATUS VALUES
# ============================================================================
STATUS_VALUES_GLOBAL = ["alpha", "beta", "gamma"]
STATUS_VALUES_SCOPE = ["pending", "active", "done"]
STATUS_VALUES_HIVE = ["todo", "doing", "review", "merged"]
STATUS_VALUES_DUPES_INPUT = ["open", "closed", "open", "closed", "pending"]
STATUS_VALUES_DUPES_EXPECTED = ["open", "closed", "pending"]

# ============================================================================
# GET-TYPES TEST CONSTANTS (raw child_tiers for multi-level config tests)
# ============================================================================
CHILD_TIERS_GLOBAL = {"t1": ["Story", "Stories"], "t2": ["Chapter", "Chapters"]}
CHILD_TIERS_SCOPE = {"t1": ["Module", "Modules"], "t2": ["Unit", "Units"]}
CHILD_TIERS_HIVE = {"t1": ["Feature", "Features"]}

# ============================================================================
# Clone Bee Tests
# ============================================================================
TICKET_ID_CLONE_BEE_ROOT = "b.cn1"  # Root bee for clone tests
TICKET_ID_CLONE_T1_1 = "t1.cn1.ab"  # First t1 child sharing cn1 prefix (period-separated: 3+2 chars)
TICKET_ID_CLONE_T1_2 = "t1.cn1.cd"  # Second t1 child sharing cn1 prefix (period-separated: 3+2 chars)
HIVE_CLONE_DEST = "clone_dest"  # Destination hive for clone tests
