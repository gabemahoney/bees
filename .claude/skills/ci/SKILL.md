---
name: ci
description: Run Docker-based end-to-end CI test against a bees worktree. Spawns one container per epic. On failure, inner Claude files a bug bee in the Bugs hive automatically.
---

# One-Time Setup

1. **Install Docker**: Install Docker Engine for your platform
2. **Start Docker**: Ensure the Docker daemon is running (`docker info` to verify)
3. **Store Anthropic API key** for Docker CI containers (they can't use OAuth):
   ```bash
   mkdir -p ~/.secrets && chmod 700 ~/.secrets
   echo -n "sk-ant-..." > ~/.secrets/anthropic_api_key
   chmod 600 ~/.secrets/anthropic_api_key
   ```
4. **Configure TestPyPI credentials** — either:
   - **~/.pypirc** (works everywhere):
     ```ini
     [testpypi]
     repository = https://test.pypi.org/legacy/
     username = __token__
     password = pypi-<your-test-pypi-token>
     ```
   - **macOS Keychain**:
     ```bash
     security add-generic-password -s "TestPyPI Token" -a testpypi -w "<your-test-pypi-token>"
     ```
5. **Install publish deps** (host-side): `pip install twine` (poetry is already available)

# Overview

Runs the bees release test suite inside Docker containers, one per epic (phase).
Before building, publishes the current code to test.pypi with a dev version.
Each phase gets a fresh container with phase-specific setup (stdio/HTTP server registration).
On failure, Claude inside the container files a bug bee against the production bees server.

The bee `b.qi9` in the `testplans` hive is the source of truth. Its child epics map to test phases:
- Phase 1: Installation & Environment
- Phase 2: CLI Exhaustive Tests — bash integration.sh run (covers all CLI tests including hive mgmt, CRUD, dependencies, queries, egg resolver, index, undertaker, move, sanitizer, etc.)
- Phase 3: Stdio Server Tests
- Phase 4: HTTP Server Tests

# Usage

```
/ci                  # Run all phases from the beginning
/ci <test-number>    # Skip to a specific test number (auto-detects phase)
```

When a test number is provided, determine which phase it belongs to by reading the test plan, skip to that phase, and pass the test number to `run_test.sh` as the second argument. Phases before the target phase are marked `finished` without running.

# Behavior

## Step 1 — Preflight

1. Docker is accessible:
   ```bash
   docker info > /dev/null 2>&1 || sg docker -c "docker info" > /dev/null 2>&1
   ```
   The `run_test.sh` script auto-detects whether `sg docker` is needed (Linux group
   permissions) and wraps its own docker calls accordingly. You do NOT need to prefix
   script invocations with `sg docker`. Just call the scripts directly.
   For direct `docker rm -f` or `docker logs` commands in this skill, use:
   ```bash
   sg docker -c "docker rm -f ..." 2>/dev/null || docker rm -f ...
   ```
   If neither `docker info` nor `sg docker -c "docker info"` works:
   "Docker is not running. Start Docker and re-run `/ci`."

2. The production bees HTTP server is reachable:
   ```bash
   curl -sf http://127.0.0.1:8000/health
   ```
   If not running, start it:
   ```bash
   bees serve --http > /tmp/bees_server.log 2>&1 &
   ```
   Wait up to 10 seconds for it to become healthy.

## Step 2 — Publish to test.pypi

Run once before any Docker builds:
```bash
./docker/publish_test_pypi.sh
```

Capture the version from the last line of output. Export it:
```bash
export BEES_VERSION=<captured-version>
```

## Step 3 — Read the bee

Use bees MCP tools:
1. `show_ticket(ticket_ids=["b.qi9"])` to get the bee
2. The `children` array contains the epic IDs in order
3. Reset all epics to status `pupa` (clean slate for this run)

The phase number is derived from the epic's position (1st child = Phase 1, etc.).

## Step 4 — Run phases

Each phase uses its own container and tmux session named `bees-ci-<N>` (e.g. `bees-ci-1`, `bees-ci-2`).

### Phase 1 — Gatekeeper (sequential)

Run Phase 1 first and wait for it to complete before launching the rest. If Phase 1 tests the install and it fails, there is no point running the other phases.

1. Set Phase 1 epic status to `worker`
2. Report: "Starting Phase 1: <epic title>"
3. Run:
   ```bash
   BEES_VERSION=${BEES_VERSION} ./docker/run_test.sh 1 [start-test-number]
   ```
   Only pass `start-test-number` if resuming from a specific test in Phase 1.
4. Tell user: `Attach with: tmux attach -t bees-ci-1`
5. Poll every 30 seconds:
   ```bash
   tmux capture-pane -t bees-ci-1 -p -S -30
   ```
6. Handle result per the rules below, then continue to parallel launch only if Phase 1 passed.

### Phases 2, 3, 4 — Parallel launch

Once Phase 1 passes, launch the remaining phases simultaneously:

1. Set all remaining epic statuses to `worker`
2. Report: "Phase 1 passed. Launching Phases 2, 3, 4 in parallel."
3. Launch each in rapid succession (no waiting between launches):
   ```bash
   BEES_VERSION=${BEES_VERSION} ./docker/run_test.sh 2
   BEES_VERSION=${BEES_VERSION} ./docker/run_test.sh 3
   BEES_VERSION=${BEES_VERSION} ./docker/run_test.sh 4
   ```
   If resuming from a specific test number and it falls in Phase N, pass it only to that phase's launch.
4. Tell user:
   ```
   Attach with:
     tmux attach -t bees-ci-2
     tmux attach -t bees-ci-3
     tmux attach -t bees-ci-4
   ```
5. Poll all three sessions every 30 seconds until each finishes:
   ```bash
   tmux capture-pane -t bees-ci-2 -p -S -30
   tmux capture-pane -t bees-ci-3 -p -S -30
   tmux capture-pane -t bees-ci-4 -p -S -30
   ```

### Monitor signals

**CRITICAL: Do NOT use `docker inspect` to detect test completion.** Containers stay running
after tests finish because the entrypoint keeps `auto_approve.sh` alive in the background.
The only reliable way to detect completion is by reading the tmux pane content.

Poll using `tmux capture-pane -t bees-ci-<N> -p -S -50` and grep for these signals:
- **`RELEASE TEST PHASE N PASSED`** — phase passed
- **`BUG FILED:`** — a test failed and a bug was filed

Only use `docker inspect` to detect container **crashes** (status=exited with non-zero exit code).
A running container does NOT mean tests are still in progress.

### Handle Result (applies to any phase)

**Phase passed:**
1. Set epic status to `finished`
2. Kill container: `docker rm -f bees-ci-<N>`
3. Kill tmux: `tmux kill-session -t bees-ci-<N>`
4. Report: "Phase N passed."

**Bug filed:**
1. Extract the ticket ID from the `BUG FILED:` line
2. Set epic status to `failed`
3. Kill container: `docker rm -f bees-ci-<N>`
4. Kill tmux: `tmux kill-session -t bees-ci-<N>`
5. Show the bug ticket (title + description)
6. Report: "Phase N failed. Bug filed as `b.XXXX`."
7. Continue monitoring remaining phases — do NOT stop them.

**Crash / timeout:**
1. Grab logs: `docker logs bees-ci-<N> --tail 30`
2. Set epic status to `failed`
3. Kill container + tmux
4. Report: "Phase N crashed. Output above."
5. Continue monitoring remaining phases — do NOT stop them.

## Step 5 — All phases passed

If all epics complete successfully:
1. Set ALL epic statuses to `legendary`
2. Report: "All phases passed. Full regression suite green."
