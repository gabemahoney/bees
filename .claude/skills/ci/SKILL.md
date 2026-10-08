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
/ci                  # Run all phases (or only failed/not-run phases if a previous run exists)
/ci full             # Force a full run from scratch, ignoring previous results
/ci <test-number>    # Skip to a specific test number (auto-detects phase)
```

**CI port:** the containers file bugs against a bees HTTP server on the host. Its port comes
from the `BEES_CI_PORT` environment variable (default `8473`). Set it to a free port if
another service already uses 8473.

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

2. The production bees HTTP server is running on the CI port, at the address the containers
   reach, and it really is bees.

   Resolve the CI port once (`BEES_CI_PORT`, default `8473`):
   ```bash
   echo "${BEES_CI_PORT:-8473}"
   ```
   Use that value as `BEES_CI_PORT` in every command below and in every `run_test.sh`
   launch.

   Resolve the bind host once. The containers reach the host through `host.docker.internal`.
   On Linux Docker Engine that name leads to the Docker bridge gateway (e.g. `172.17.0.1`),
   and the containers cannot reach a server bound to `127.0.0.1`. On Docker Desktop it leads
   to the host's `127.0.0.1`. The helper prints the right address: the bridge gateway if it is
   an address of this host, otherwise `127.0.0.1`. It never prints `0.0.0.0`, which would
   expose the server on every network.
   ```bash
   { docker network inspect bridge 2>/dev/null || sg docker -c "docker network inspect bridge" 2>/dev/null; } | python3 docker/ci_bind_host.py 2>/dev/null
   ```
   It prints a single line, a bare IPv4 address. Use it as `<bind-host>` in every command below.

   Shell variables may not persist between commands, so write the literal port and bind host
   wherever `${BEES_CI_PORT}` and `<bind-host>` appear.

   Check the server identity at the bind host. Do not rely on `/health`: another service on
   the same port may answer it too. The check sends an MCP `initialize` request and accepts
   only a server that names itself `bees`:
   ```bash
   python3 docker/check_bees_server.py "http://<bind-host>:${BEES_CI_PORT}"
   ```
   Branch on the exit code:
   - **0**: bees confirmed. It was running before `/ci` began. Either the user started it, or
     an earlier `/ci` run started it and was interrupted before it could stop it. The PID
     record tells them apart. If `/tmp/bees_ci_server.pid` exists, show the recorded process,
     if it is still running (this only looks, it stops nothing):
     ```bash
     ps -p "$(cat /tmp/bees_ci_server.pid)" -o pid=,args=
     ```
     - If the command line it prints contains `bees serve --http --host <bind-host> --port <port>`,
       an earlier `/ci` run started this server. Keep the record and continue: this run stops
       that server when it ends (see "Stop the bees server /ci started").
     - Otherwise (there is no record, the command printed nothing, or it printed another
       command), the user started this server, and `/ci` must never stop it. Delete the stale
       record, then continue:
       ```bash
       rm -f /tmp/bees_ci_server.pid
       ```
   - **1**: nothing is listening at the bind host. Start bees there. Always pass `--host` and
     `--port`: the default host `127.0.0.1` is unreachable from the containers on Linux Docker
     Engine, and `http.port` in the global config must not move the server to another port.
     The same command records the PID of the server `/ci` started, so that `/ci` can stop it
     when the run ends (see "Stop the bees server /ci started"):
     ```bash
     bees serve --http --host <bind-host> --port "${BEES_CI_PORT}" > /tmp/bees_server.log 2>&1 & echo $! > /tmp/bees_ci_server.pid
     ```
     Then wait up to 10 seconds for it to be confirmed:
     ```bash
     python3 docker/check_bees_server.py --wait 10 "http://<bind-host>:${BEES_CI_PORT}"
     ```
     If this does not exit 0, show `tail -20 /tmp/bees_server.log` and the check output, stop
     the bees server /ci started, then STOP:
     "The bees HTTP server did not start on <bind-host> port <port>."
   - **2**: the connection was not refused, but no bees MCP server answered. Never kill, signal,
     or reconfigure whatever holds the port. Tell the user, with the one-line reason the check
     printed on stderr, then STOP:
     "Whatever is on <bind-host> port <port> did not identify itself as bees: <reason>. Re-run
     `/ci` with a free port, e.g. with `BEES_CI_PORT=<free-port>` set in the environment. If it
     is a stuck bees server you own, restart it yourself, then re-run `/ci`."
   - **3**: usage error. If the resolved port is not an integer from 1 to 65535, STOP and tell
     the user: "`BEES_CI_PORT` is invalid (<value>): it must be an integer from 1 to 65535."
     Otherwise fix the check command and re-run the check.

   `run_test.sh` repeats this check from inside a container, against the URL the containers
   use, and exits non-zero before the phase starts if the containers cannot reach bees there
   (for example, when a host firewall blocks container-to-host traffic). Step 4 says how to
   handle that.

## Step 2 — Publish to test.pypi

Run once before any Docker builds:
```bash
./docker/publish_test_pypi.sh
```

If it exits non-zero, show its output, stop the bees server /ci started, then STOP:
"Publishing to test.pypi failed: <the error publish_test_pypi.sh printed>."

Capture the version from the last line of output. Export it:
```bash
export BEES_VERSION=<captured-version>
```

## Step 3 — Read the bee and determine which phases to run

Use bees MCP tools:
1. `show_ticket(ticket_ids=["b.qi9"])` to get the bee
2. The `children` array contains the epic IDs in order
3. `show_ticket` on all children to read their current statuses

The phase number is derived from the epic's position (1st child = Phase 1, etc.).

**Determine run scope:** Unless the argument is `full`, check epic statuses from
the previous run:
- `finished` or `legendary` = previously passed. **Skip these phases.**
- `failed` or `pupa` = needs to run.
- `worker` = was in progress when the last run was interrupted. Needs to run.

If ALL phases are already `finished`/`legendary`, treat this as a fresh run
(reset all to `pupa`). Otherwise, only reset the phases that need to run to `pupa`.

Report which phases will run and which are being skipped:
```
Skipping phases 1, 2, 3, 5 (passed in previous run).
Running phases 4, 6.
```

If the argument is `full`, reset ALL epics to `pupa` and run everything.

## Step 4 — Run phases

Each phase uses its own container and tmux session named `bees-ci-<N>` (e.g. `bees-ci-1`, `bees-ci-2`).

### Phase 1 — Gatekeeper (sequential)

Run Phase 1 first and wait for it to complete before launching the rest. If Phase 1 tests the install and it fails, there is no point running the other phases.

If Phase 1 was already `finished`/`legendary` from a previous run, skip it and go
straight to launching the remaining phases that need to run.

1. Set Phase 1 epic status to `worker`
2. Report: "Starting Phase 1: <epic title>"
3. Run:
   ```bash
   BEES_CI_PORT=${BEES_CI_PORT} BEES_VERSION=${BEES_VERSION} ./docker/run_test.sh 1 [start-test-number]
   ```
   Only pass `start-test-number` if resuming from a specific test in Phase 1.
   If it exits non-zero, handle it as a launch failure (see "Launch failure" below) and skip
   the remaining steps.
4. Tell user: `Attach with: tmux attach -t bees-ci-1`
5. Poll every 30 seconds:
   ```bash
   tmux capture-pane -t bees-ci-1 -p -S -30
   ```
6. Handle result per the rules below, then continue to parallel launch only if Phase 1 passed.
   If Phase 1 did not pass, the run ends here: stop the bees server /ci started.

### Phases 2, 3, 4 — Parallel launch

Once Phase 1 passes, launch the remaining phases simultaneously:

1. Set all remaining epic statuses to `worker`
2. Report: "Phase 1 passed. Launching Phases 2, 3, 4 in parallel."
3. Launch the phases one after another, each as its own command. Never combine the launches
   into one command: it reports only the exit status of the last launch. Each launch returns
   once its container and tmux session are up, without waiting for the tests, so the phases
   still run in parallel. Wait only for the launch command to return, then check its exit
   status before starting the next launch.
   ```bash
   BEES_CI_PORT=${BEES_CI_PORT} BEES_VERSION=${BEES_VERSION} ./docker/run_test.sh 2
   ```
   ```bash
   BEES_CI_PORT=${BEES_CI_PORT} BEES_VERSION=${BEES_VERSION} ./docker/run_test.sh 3
   ```
   ```bash
   BEES_CI_PORT=${BEES_CI_PORT} BEES_VERSION=${BEES_VERSION} ./docker/run_test.sh 4
   ```
   If resuming from a specific test number and it falls in Phase N, pass it only to that phase's launch.
   If a launch exits non-zero, do not start the launches that remain. Handle it as a launch
   failure (see "Launch failure" below) and skip the remaining steps.
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
6. Once every phase has a result: if all passed, go to Step 5. Otherwise the run ends here:
   stop the bees server /ci started.

### Launch failure

`run_test.sh` exits non-zero when a pre-flight check fails (for example: no Claude auth, Docker
not accessible, no bees server confirmed at the bind host or from inside a container) or when
the image build or container start fails. The phase did not start, so there is nothing to poll.
All phases share the one bees server and image, so the failure would repeat in every phase:

1. Show the full `run_test.sh` output to the user.
2. Remove the containers and tmux sessions of every phase in this launch (Phase 1 alone, or
   all phases of the parallel launch, including any already running). Both commands are
   harmless if nothing exists:
   ```bash
   docker rm -f bees-ci-<N>
   tmux kill-session -t bees-ci-<N>
   ```
3. Set the epic status of every phase in this launch to `failed`.
4. Stop the bees server /ci started.
5. STOP: "Phase N could not start: <the error run_test.sh printed>." For a parallel launch,
   add: "Phases <list> were stopped or not started."

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
2. Stop the bees server /ci started.
3. Report: "All phases passed. Full regression suite green."

## Stop the bees server /ci started

The bees HTTP server has no authentication. On Linux Docker Engine it listens on the Docker
bridge address, where every container on this host can reach it. So when `/ci` started the
server (Step 1, exit code 1), or an interrupted earlier `/ci` run started it and left its PID
record behind (Step 1, exit code 0, record kept), this run stops it as soon as the run ends:
in Step 5, after the last phase result when not all phases passed, and before every STOP (or
any other early end of the run) once Step 1 has started the server or kept the record.

The only process `/ci` ever stops is one that a `/ci` run launched, identified by the PID that
run recorded. Never stop a server the user started (Step 1, exit code 0, record deleted), and
never kill, signal, or reconfigure anything else that holds the port.

1. If `/tmp/bees_ci_server.pid` does not exist, `/ci` did not start the server: do nothing.
2. Show the recorded process, if it is still running:
   ```bash
   ps -p "$(cat /tmp/bees_ci_server.pid)" -o pid=,args=
   ```
3. Only if the command line it prints contains
   `bees serve --http --host <bind-host> --port <port>`, stop that PID:
   ```bash
   kill <pid>
   ```
   If it prints nothing (the server already exited) or another command (the PID was reused),
   kill nothing.
4. Delete the record:
   ```bash
   rm -f /tmp/bees_ci_server.pid
   ```
