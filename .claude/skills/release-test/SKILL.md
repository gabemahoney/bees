---
name: release-test
description: Run one phase of the bees release test suite. Execute tests one by one, report results, file bugs on failure.
---

# Release Test Runner

You are a strict test runner. Execute each test from the test plan one at a time.
IMPORTANT: Never try to fix problems or work around issues. If something is broken stop and FILE A BUG.

## Phase

Check the `$PHASE` environment variable to determine which phase to run (1, 2, 3, or 4).

## Fetching the Test Plan

The test plan lives in the local bees ticket system (the `testplans` hive was pre-populated before you started). Use the **`bees`** MCP server.

The hierarchy is: `b.qi9 (bee) → t1 (phase) → t2 (test area) → t3 (individual test)`

1. Call `show_ticket(["b.qi9"])` on `bees` to get the root bee
2. `children` is an ordered list of t1 phase IDs — position maps to phase: children[0] = Phase 1, children[1] = Phase 2, etc.
3. Call `show_ticket([phase_id])` for the t1 matching `$PHASE` to get its `children` (the t2 test area IDs)
4. Call `show_ticket(all_t2_ids)` in one batch to load all test area tickets
5. Collect all `children` from every t2 — these are the t3 individual test IDs
6. Call `show_ticket(all_t3_ids)` in one batch to load all individual test tickets
7. Sort tests in `up_dependencies` order so they execute in the correct sequence

Each t3 test ticket contains:
- `title`: the test name (e.g. "Test 47: Linter flags invalid status when status_values configured")
- `description`: the full test instructions — what to run and what to verify
- `up_dependencies`: tickets that must run before this one (used for skip-ahead dependency resolution)

## Test Execution Order

Execute each test in the order they appear (sorted by dependency chain). The test number is embedded in the title.

## Start at test N (optional)

If invoked as `/release-test N` (where N is a test number), skip to test N using the following algorithm. Check the `$START_TEST` environment variable as a fallback if no argument is provided.

### Skip-ahead algorithm

1. Collect the full transitive closure of `up_dependencies` for test N — i.e. the dependencies of dependencies, recursively. Call this set **required**.
2. For each test K in **required** (in dependency order): run it as a real test (full pass/fail). If it fails, file a bug and stop.
3. Skip all other tests before N entirely. Do not run them, do not replay their commands. Print `[skipped] Test K: <name>` for each.
4. Run test N.
5. Continue running all tests after N normally.

**The `up_dependencies` field is the source of truth for execution order** — the `children[]` array of a Test Area is not ordered and must not be used for sequencing. If a test has no `up_dependencies`, it has no prerequisites and can run directly. Do not run prior tests "for state" unless they appear in the dependency graph.

**The transitive closure is always local to one Test Area.** Test cases never have `up_dependencies` pointing outside their own Test Area — cross-area state dependencies are forbidden by convention. You will never need to run tests from another area as prerequisites.

## Rules

- Run each command directly. Do NOT write scripts or batch tests together.
- After each test print exactly: `[N/TOTAL] PASS: <name>` or `[N/TOTAL] FAIL: <name> — <error>`
  - N counts from 1 within the phase. TOTAL is the number of tests in this phase.
- The working directory is /test-repo. It is NOT a git repo — this is intentional. Bees does not require git. Do NOT run git init or any git commands.
- Do NOT use `--test-config` unless a specific test says to. You are inside a disposable Docker container — that IS the isolation. Use bees commands bare.
- Do NOT create a "plan" or "strategy" before running tests. Just start with the first test and go.
- Install bees from **test.pypi**, NOT from /src. The version is in `$BEES_VERSION`.
- For Phase 1 install:
  ```bash
  pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ bees-md==${BEES_VERSION}
  ```
- When tests need the serve extra (Phase 3/4), install with:
  ```bash
  pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ 'bees-md[serve]==${BEES_VERSION}'
  ```
- Do NOT use `pip install /src` anywhere.

## On Success

When all tests in the phase pass, print:

```
RELEASE TEST PHASE {N} PASSED
```

Where {N} is the phase number from `$PHASE`.

## On Failure

If any test fails, do the following **immediately**:

1. Print the FAIL line
2. File a bug using `file_bug.py`. Include: the test name, test number, the exact command that was run, the full error output, and any diagnostic context:
   ```bash
   python /usr/local/bin/file_bug.py \
     --title "[ci] TEST_NAME" \
     --description "Phase N, Test M: DETAILED_DESCRIPTION

   Command: THE_EXACT_COMMAND_RUN
   Expected: WHAT_WAS_EXPECTED
   Got: THE_ACTUAL_OUTPUT

   Context: ANY_RELEVANT_DIAGNOSTIC_INFO"
   ```
3. The script prints `BUG FILED: b.XXXX` on success. Report that ticket ID.
4. Exit immediately — do NOT continue testing. Do NOT debug or work around the failure.
