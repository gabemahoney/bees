---
name: ci
description: Run Docker-based end-to-end CI test against a bees worktree. Spawns one container per epic. On failure, the container files a bug bee in this repo's bugs hive automatically.
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
On failure, the container files a bug bee into this repo's bugs hive, through the production bees
server (see "Bugs hive" below).

The bee `b.qi9` in the `testplans` hive is the source of truth. The containers run the copy of it
in this checkout's `docker/testplans`, and `/ci` reads and records phase statuses in that same
copy only (see Step 3). Its child epics are the test phases, in order: the 1st child is Phase 1,
the 2nd is Phase 2, and so on. The plan can have any number of phases, so this skill never
assumes a count: the phase list comes from `docker/ci_plan.py` (Step 3), which reads b.qi9's
children, and `/ci` runs every phase in it. Phase 1, the first phase, is the gatekeeper (Step 4).
For example, Phase 1 tests installation and the environment, and later phases include CLI tests
run by `tests/integration.sh` and MCP server tests run by Claude; `ci_plan.py` lists them all.

# Usage

```
/ci                  # Run all phases; when phase statuses are recorded (status hive, Step 3), only failed/not-run phases if a previous run exists
/ci full             # Force a full run from scratch, ignoring previous results
/ci <test-number>    # Skip to a specific test number (auto-detects phase)
```

**CI port:** the containers file bugs against a bees HTTP server on the host. Its port comes
from the `BEES_CI_PORT` environment variable (default `8473`). Set it to a free port if
another service already uses 8473.

**Bugs hive:** a failing test files its bug into this repo's bugs hive on the host, through the
bees server on the CI port. Hive names and paths differ between machines, so nothing is built
in: `run_test.sh` finds both values below on the host and passes them into the container.
- `BEES_REPO_ROOT`: the host directory the bees server picks this repo's hives by (default:
  this checkout).
- `BEES_BUGS_HIVE`: the hive to file into (default: from `bees list-hives` run in
  `BEES_REPO_ROOT`, in the most specific scope matching it that has one, the hive named `bugs`,
  else the only hive whose name contains `bugs`; inherited scopes count only after this repo's own).

Set either one in the environment to override it. If no bugs hive is found, `run_test.sh`
stops before the phase starts (see "Launch failure").

**Phase timeout:** a phase that shows no result within `BEES_CI_PHASE_TIMEOUT_MINUTES` minutes
of its launch (default `60`) is handled as crashed (see "Crash / timeout"), so a phase that
never reports cannot hang `/ci`. Raise it if a phase legitimately runs longer.

When a test number is provided, determine which phase it belongs to by reading this checkout's
plan files (see Step 3), skip to that phase, and pass the test number to `run_test.sh` as the
second argument. Phases before the target phase do not run; with a status hive (Step 3), they are
marked `finished`.

Run every command in this skill from this checkout's root, the directory holding `docker/`: the
`bees` commands pick hives by the directory they run in.

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

2. Resolve the phase timeout once (`BEES_CI_PHASE_TIMEOUT_MINUTES`, default `60`):
   ```bash
   echo "${BEES_CI_PHASE_TIMEOUT_MINUTES:-60}"
   ```
   If it is not a whole number greater than 0, STOP and tell the user:
   "`BEES_CI_PHASE_TIMEOUT_MINUTES` is invalid (<value>): it must be a whole number of minutes greater than 0."
   Use the value as `<timeout-minutes>` below.

3. The production bees HTTP server is running on the CI port, at the address the containers
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

## Step 3 — Read the test plan and determine which phases to run

The containers run the plan in this checkout's `docker/testplans` (`run_test.sh` mounts it), so
`/ci` reads that same copy, from its files. Never read or update the plan through the bees MCP
tools, or through a bees command other than the status write under "Phase statuses": the host's
registered `testplans` hive may be another copy (in a worktree, usually the main checkout's), and
on another machine `docker/testplans` may not be registered at all.

Read the plan:
```bash
bees list-hives | python3 docker/ci_plan.py
```
If it exits non-zero, show its error, stop the bees server /ci started, then STOP:
"Cannot read the test plan: <the error ci_plan.py printed>."

It prints JSON:
- `phases`: the epics of `b.qi9` in order, each with `phase` (1st child = Phase 1, etc.), `id`,
  `title` and `status`. This is the complete list of phases, however many there are: the run
  scope (below) and Step 4 work from it, never from a fixed phase count.
- `status_hive`: the hive `/ci` records phase statuses through, or `null`. `status_hive_reason`
  says why.

To find the phase of a test number `<N>`, search the same files:
```bash
grep -rlE "^title: '?Test <N>:" docker/testplans/b.qi9
```
The epic is the directory right below `docker/testplans/b.qi9/` in the path it prints. If it prints
nothing, the phase is the one whose epic body says `Tests in this phase: <first>-<last>` (or
`<first>–<last>`) with `<N>` in that range (read `docker/testplans/b.qi9/<epic-id>/<epic-id>.md`).

### Phase statuses

With a status hive, `/ci` records each phase's progress and result as its epic's status, and the
next run reads them to skip the phases that passed. It writes them through bees, and only into
this checkout's copy: `status_hive` is a hive that bees, run from this checkout's root, resolves
to this checkout's `docker/testplans`. `ci_plan.py` matches the hives by path, never by name.

- **`status_hive` set:** every step in this skill that sets or resets epic statuses means, with
  the epic IDs from `phases`:
  ```bash
  bees update-ticket --ids <epic-id> [<epic-id> ...] --status <status> --hive <status_hive>
  ```
  If its output does not have `"status": "success"`, or lists an ID under `not_found` or `failed`,
  tell the user "Could not record `<status>` for Phase N: <error>." and continue: the status is a
  record, not a test result.
- **`status_hive` null:** `/ci` records nothing. Skip every step that sets or resets epic statuses,
  and never write the epics through another hive or the bees MCP tools: that would change a copy
  the containers do not run. Tell the user once:
  "Phase statuses will not be recorded: <status_hive_reason>. Running all phases."
  Run every phase, as with `full`: no run can update the statuses in these files, so skipping by
  them would skip the same phases every time. A test number still applies: the phases before its
  phase do not run.

**Determine run scope:** the run scope is the set of phases this run runs. Step 4 runs exactly
those and skips the rest. It never skips a phase for the status its plan file shows: without a
status hive, nothing updates those statuses, so they can be left from any earlier run or commit.
A test number leaves the phases before its phase out of the run scope (see "Usage").

Without a status hive, the run scope is every phase that a test number does not leave out: no
phase is skipped for its status (see "Phase statuses" above).

With a status hive, unless the argument is `full`, check epic statuses from the previous run:
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

Run the phases in the run scope (Step 3), by their `phase` numbers in the `phases` list that
`ci_plan.py` printed. Never assume how many phases there are: every phase in that list that is in
the run scope runs. Each phase `<N>` uses its own container and tmux session named `bees-ci-<N>`
(e.g. `bees-ci-1`, `bees-ci-2`).

The gatekeeper is the first phase, Phase 1: it runs alone, first. Then every other phase in the
run scope is launched in parallel.

### Phase 1 — Gatekeeper (sequential)

Run Phase 1, the plan's first phase, first and wait for it to complete before launching the rest.
If Phase 1 tests the install and it fails, there is no point running the other phases.

If Step 3 left Phase 1 out of the run scope, skip it and go straight to launching the remaining
phases in the run scope. Otherwise run it, whatever status its plan file shows.

1. Set Phase 1 epic status to `worker`
2. Report: "Starting Phase 1: <epic title>"
3. Run:
   ```bash
   BEES_CI_PORT=${BEES_CI_PORT} BEES_VERSION=${BEES_VERSION} ./docker/run_test.sh 1 [start-test-number]
   ```
   Only pass `start-test-number` if resuming from a specific test in Phase 1.
   If it exits non-zero, handle it as a launch failure (see "Launch failure" below) and skip
   the remaining steps.
4. Record the phase's deadline. Once the launch returns, run:
   ```bash
   date +%s
   ```
   The deadline is that number plus `<timeout-minutes>` × 60.
5. Tell user: `Attach with: tmux attach -t bees-ci-1`
6. Poll every 30 seconds, comparing the time with the deadline (see "Monitor signals"):
   ```bash
   tmux capture-pane -t bees-ci-1 -p -S -30
   date +%s
   ```
7. Handle result per the rules below, then continue to the parallel launch only if Phase 1
   passed. If Phase 1 passed and no other phase is in the run scope, go to Step 5.
   If Phase 1 did not pass, the run ends here: stop the bees server /ci started.

### Remaining phases — Parallel launch

Once Phase 1 passes (or Step 3 left it out of the run scope), launch every remaining phase in the
run scope simultaneously: all phases after Phase 1 in the `phases` list, however many there are.
Leave every phase outside the run scope out of the steps below:

1. Set all remaining epic statuses to `worker`
2. Report: "Phase 1 passed. Launching Phases <list> in parallel.", where `<list>` is the phase
   numbers being launched (e.g. "Launching Phases 2, 3, 4, 5, 6 in parallel."). If Step 3 left
   Phase 1 out of the run scope, leave out "Phase 1 passed."
3. Launch the phases one after another, in phase order, each as its own command: run the
   command below once per phase, with that phase's number as `<N>`. Never combine the launches
   into one command: it reports only the exit status of the last launch. Each launch returns
   once its container and tmux session are up, without waiting for the tests, so the phases
   still run in parallel. Wait only for the launch command to return, then check its exit
   status before starting the next launch.
   ```bash
   BEES_CI_PORT=${BEES_CI_PORT} BEES_VERSION=${BEES_VERSION} ./docker/run_test.sh <N>
   ```
   If resuming from a specific test number and it falls in Phase N, pass it only to that phase's
   launch, as the second argument.
   If a launch exits non-zero, do not start the launches that remain. Handle it as a launch
   failure (see "Launch failure" below) and skip the remaining steps.
   Record each phase's deadline as soon as its launch returns, before the next launch: run
   `date +%s`. The deadline is that number plus `<timeout-minutes>` × 60.
4. Tell user, with one `tmux attach` line per launched phase:
   ```
   Attach with:
     tmux attach -t bees-ci-<N>
   ```
5. Poll every launched session every 30 seconds until each finishes, comparing the time with
   each phase's deadline (see "Monitor signals"). Use one `tmux capture-pane` line per launched
   phase, then one `date +%s`:
   ```bash
   tmux capture-pane -t bees-ci-<N> -p -S -30
   date +%s
   ```
6. Once every launched phase has a result: if all passed, go to Step 5. Otherwise the run ends
   here: stop the bees server /ci started.

### Launch failure

`run_test.sh` exits non-zero when a pre-flight check fails (for example: test plan `b.qi9`
missing from this checkout's `docker/testplans`, no bugs hive found, no Claude auth, Docker not
accessible, no bees server confirmed at the bind host or from inside a container) or when the
image build or container start fails. The phase did not start, so there is nothing to poll.
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
after tests finish: the test session in the container stays open, with its last output on
screen, until `/ci` removes the container.
The only reliable way to detect completion is by reading the tmux pane content.

Poll using `tmux capture-pane -t bees-ci-<N> -p -S -50` and grep for these signals. The first
two are results: check them first, since the others can appear below them.
- **`RELEASE TEST PHASE N PASSED`** — phase passed
- **`BUG FILED:`** — a test failed and a bug was filed
- **`BUG FILING FAILED:`** — a test failed, but its bug could not be filed (the line says why): crash
- **`TEST RUNNER EXITED`** — the test runner ended without either result: crash
- **`--- Phase N exited`** — the host session lost the container's session (for example the
  container stopped): crash

Then compare the time (`date +%s`) with the phase's deadline. A phase with none of these
signals at or past its deadline has timed out: crash.

Only use `docker inspect` to detect container **crashes** (the container is no longer running).
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

**Crash / timeout** (`BUG FILING FAILED:`, `TEST RUNNER EXITED`, `--- Phase N exited`, a
stopped container, or the deadline passed with no result):
1. Grab output: `tmux capture-pane -t bees-ci-<N> -p -S -50` and `docker logs bees-ci-<N> --tail 30`
2. Set epic status to `failed`
3. Kill container + tmux
4. Report by cause:
   - Bug filing failed: "Phase N failed, but its bug could not be filed: <the reason on the
     `BUG FILING FAILED:` line>. Output above."
   - Timeout: "Phase N timed out: no result after <timeout-minutes> minutes. Output above."
   - Otherwise: "Phase N crashed. Output above."
5. Continue monitoring remaining phases — do NOT stop them.

## Step 5 — All phases passed

If every phase in the run scope (Step 3) passed:
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
